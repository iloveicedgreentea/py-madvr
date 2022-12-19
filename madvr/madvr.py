"""
Implements the MadVR protocol
"""

import logging
from typing import Final, Union
import asyncio
import time
from madvr.commands import ACKs, Footer, Headers, Commands, Enum, Connections


class Madvr:
    """MadVR Control"""

    def __init__(
        self,
        host: str,
        # Can supply a logger object. It can hook into the HA logger
        logger: logging.Logger = logging.getLogger(__name__),
        port: int = 44077,
        connect_timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.connect_timeout: int = connect_timeout
        self.logger = logger
        self._lock = asyncio.Lock()
        # Const values
        self.MADVR_OK: Final = Connections.welcome.value
        self.HEARTBEAT: Final = Connections.heartbeat.value
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.read_limit = 8000
        self.command_read_timeout = 3
        self.logger.debug("Running in debug mode")
    async def async_open_connection(self) -> bool:
        """Open a connection"""
        self.logger.debug("Starting open connection")
        msg, success = await self.reconnect()

        if not success:
            self.logger.error(msg)

        return success

    async def reconnect(self):
        """Initiate keep-alive connection. This should handle any error and reconnect eventually."""
        while True:
            try:
                if self.writer is not None:
                    self.logger.debug("Closing writer")
                    self.writer.close()
                    await self.writer.wait_closed()
                self.logger.info(
                    "Connecting to MadVR: %s:%s", self.host, self.port
                )
                cor = asyncio.open_connection(self.host, self.port)
                # wait for 10 sec to connect
                self.reader, self.writer = await asyncio.wait_for(cor, 10)
                self.logger.info("Connected to Envy")
                # create a reader and writer to do handshake
                self.logger.debug("Handshaking")
                result, success = await self._async_handshake()
                if not success:
                    return result, success
                self.logger.debug("Handshake complete and we are connected")
                return "Connection done", True

            # includes conn refused
            except OSError as err:
                self.logger.warning("Connecting failed, retrying in 2 seconds")
                self.logger.debug(err)
                await asyncio.sleep(2)
            except asyncio.TimeoutError:
                self.logger.warning("Connection timed out, retrying in 2 seconds")
                await asyncio.sleep(2)

    async def _async_handshake(self) -> tuple[str, bool]:
        """
        Make sure we got a handshake, make sure we can send heartbeat
        """
        # Make sure first message says WELCOME
        msg_envy = await self.reader.read(self.read_limit)
        self.logger.debug(self.MADVR_OK)
        self.logger.debug(msg_envy[:7])
        # Check if first 7 char match
        if self.MADVR_OK != msg_envy[:7]:
            result = f"Envy did not reply with correct greeting: {msg_envy}"
            self.logger.error(result)
            return result, False

        # # try sending heartbeat, if there's an error, raise exception
        # try:
        #     time.sleep(20)
        #     self.logger.debug(self.HEARTBEAT)
        #     self.writer.write(self.HEARTBEAT)
        #     await self.writer.drain()
        # except asyncio.TimeoutError as err:
        #     result = f"Timeout sending heartbeat {err}"
        #     self.logger.error(result)
        #     return result, False

        # # see if we receive PJACK, if not, raise exception
        # self.logger.debug("Waiting for heartbeat ok")
        # time.sleep(1)
        # msg_hb = await self.reader.read(self.read_limit)
        # if msg_hb != ACKs.reply.value:
        #     result = f"Exception with heartbeat: {msg_hb}"
        #     self.logger.error(result)
        #     return result, False
        # self.logger.debug("Handshake successful")
        return "ok", True

    async def async_keep_open(self):
        await self.reconnect()

        i = 0
        while i < 10:
            self.writer.write("Heartbeat\r".encode("utf-8"))
            await self.writer.drain()
            print(await self.reader.read(4000))
            time.sleep(20)
            i += 1
        # await self.writer.close()

    async def async_send_command(self, command: str) -> str:
        await self.reconnect()
        self.writer.write(command.encode("utf-8"))
        try:
            await self.writer.drain()
            time.sleep(1)
            # TODO: need a way to constantly read stuff from input somehow?
            # TODO: maybe always sleep and then read a ton and filter from Response header to \r\n
            return await self.reader.read(self.read_limit)
        except asyncio.TimeoutError as err:
            result = f"Timeout sending command {err}"
            self.logger.error(result)
            return result, False
        except ConnectionError as err:
            # reaching this means the writer was closed somewhere
            self.logger.error(err)
            self.logger.debug("Restarting connection")
            # restart the connection

        await self.reconnect()
    # async def _async_construct_command(
    #     self, raw_command: str
    # ) -> tuple[bytes, ACKs]:
    #     """
    #     Transform commands into their byte values from the string value
    #     """
    #     # split command into the base and the action like command // params
    #     try:
    #         command, value = raw_command.split(",")
    #     except ValueError:
    #         command = raw_command
    #         value = ""
    #         # return "No value for command provided", False

    #     # Check if command is implemented
    #     if not hasattr(Commands, command):
    #         self.logger.error("Command not implemented: %s", command)
    #         return "Not Implemented", False

    #     # construct the command with nested Enums
    #     command_name, ack = Commands[command].value
    #     # Construct command based on required values
    #     command: bytes = (
    #         command_name + Footer.footer.value
    #     )
    #     self.logger.debug("command: %s", command)

    #     return command, ack

    # async def _async_send_command(
    #     self,
    #     send_command: Union[list[bytes], bytes],
    #     ack: bytes = None,
    # ) -> tuple[str, bool]:
    #     """
    #     Sends a command with a flag to expect an ack.

    #     The PJ API returns nothing if a command is in flight
    #     or if a command is not successful

    #     send_command: A command to send
    #     ack: value of the ack we expect, like OK

    #     Returns:
    #         (
    #             ack or error message: str,
    #             success flag: bool
    #         )
    #     """

    #     if self.writer is None:
    #         self.logger.error("Connection lost. Restarting")

    #         await self.reconnect()

    #     try:
    #         cons_command, ack = await self._async_construct_command(
    #             send_command
    #         )
    #     except TypeError:
    #         cons_command = send_command

    #     if not ack:
    #         return cons_command, ack

    #     result, success = await self._async_do_command(
    #         cons_command, ack.value
    #     )

    #     return result, success

    # async def _async_do_command(
    #     self,
    #     command: bytes,
    #     ack: bytes,
    # ) -> tuple[str, bool]:
    #     retry_count = 0
    #     while retry_count < 5:
    #         self.logger.debug("do_command sending command: %s", command)
    #         # send the command
    #         self.writer.write(command)
    #         try:
    #             await self.writer.drain()
    #         except asyncio.TimeoutError as err:
    #             result = f"Timeout sending command {err}"
    #             self.logger.error(result)
    #             return result, False
    #         except ConnectionError as err:
    #             # reaching this means the writer was closed somewhere
    #             self.logger.error(err)
    #             self.logger.debug("Restarting connection")
    #             # restart the connection

    #             await self.reconnect()
    #             self.logger.debug("Sending command again")
    #             # restart the loop
    #             retry_count += 1
    #             continue

    #         # if we send a command that returns info, the projector will send
    #         # an ack, followed by the actual message. Check to see if the ack sent by
    #         # projector is correct, then return the message.
    #         ack_value = (
    #             ack + Footer.footer.value
    #         )
    #         self.logger.debug("constructed ack_value: %s", ack_value)

    #         # see if we receive PJACK, if not, raise exception
    #         self.logger.debug("Waiting for command ok")
    #         msg_hb = await self.reader.read(4000)
    #         if msg_hb != ACKs.reply.name:
    #             result = f"Exception with heartbeat: {msg_hb}"
    #             self.logger.error(result)
    #             return result, False
    #         self.logger.debug("Command successful")
    #         # # Receive the acknowledgement from PJ
    #         # try:
    #         #     # seems like certain commands timeout when PJ is off
    #         #     received_ack = await asyncio.wait_for(
    #         #         self.reader.readline(), timeout=self.command_read_timeout
    #         #     )
    #         # except asyncio.TimeoutError:
    #         #     # LL is used in async_update() and I don't want to spam HA logs so we skip
    #         #     # if not command == b"?\x89\x01PMLL\n":
    #         #     # Sometimes if you send a command that is greyed out, the PJ will just hang
    #         #     self.logger.error(
    #         #         "Connection timed out. Command %s is probably not allowed to run at this time.",
    #         #         command,
    #         #     )
    #         #     self.logger.debug("restarting connection")

    #         #     await self.reconnect()
    #         #     retry_count += 1
    #         #     continue

    #         # except ConnectionRefusedError:
    #         #     self.logger.error("Connection Refused when getting ack")
    #         #     self.logger.debug("restarting connection")

    #         #     await self.reconnect()
    #         #     retry_count += 1
    #         #     continue

    #         # self.logger.debug("received ack from PJ: %s", received_ack)

    #         # # This will probably never happen since we are handling timeouts now
    #         # if received_ack == b"":
    #         #     self.logger.error("Got a blank ack. Restarting connection")

    #         #     await self.reconnect()
    #         #     retry_count += 1
    #         #     continue

    #         # # get the ack for operation
    #         # if received_ack == ack_value:
    #         #     return received_ack, True

    #         # # if we got what we expect and this is a reference,
    #         # # receive the data we requested
    #         # if received_ack == ack_value:
    #         #     message = await self.reader.readline()
    #         #     self.logger.debug("received message from PJ: %s", message)

    #         #     return message, True

    #         # # Otherwise, it failed
    #         # # Because this now reuses a connection, reaching this stage means catastrophic failure, or HA running as usual :)
    #         # self.logger.error(
    #         #     "Recieved ack did not match expected ack: %s != %s",
    #         #     received_ack,
    #         #     ack_value,
    #         # )
    #         # # Try to restart connection, if we got here somethihng is out of sync

    #         await self.reconnect()
    #         retry_count += 1
    #         continue

    #     self.logger.error("retry count for running commands exceeded")
    #     return "retry count exceeded", False

    
    # def exec_command(
    #     self, command: Union[list[str], str], command_type: bytes = b"!"
    # ) -> tuple[str, bool]:
    #     """
    #     Sync wrapper for async_exec_command
    #     """

    #     return asyncio.run(self.async_exec_command(command, command_type))

    # async def async_exec_command(
    #     self, command: Union[list[str], str], command_type: bytes = b"!"
    # ) -> tuple[str, bool]:
    #     """
    #     Wrapper for _send_command()

    #     command: a str of the command and value, separated by a comma ("power,on").
    #         or a list of commands
    #     This is to make home assistant UI use easier
    #     command_type: which operation, like ! or ?

    #     Returns
    #         (
    #             ack or error message: str,
    #             success flag: bool
    #         )
    #     """
    #     self.logger.debug("exec_command Executing command: %s", command)
    #     return await self._async_send_command(command, command_type)

    # def power_off(
    #     self,
    # ) -> tuple[str, bool]:
    #     """
    #     sync wrapper for async_power_off
    #     """
    #     return asyncio.run(self.async_power_off())

    # async def async_power_off(self) -> tuple[str, bool]:
    #     """
    #     Turns off PJ
    #     """
    #     return await self.async_exec_command("power_off")
    
    # async def _async_replace_headers(self, item: bytes) -> bytes:
    #     """
    #     Will strip all headers and returns the value itself
    #     """
    #     headers = [x.value for x in Header] + [x.value for x in Footer]
    #     for header in headers:
    #         item = item.replace(header, b"")

    #     return item

    # async def _async_do_reference_op(self, command: str, ack: ACKs) -> tuple[str, bool]:
    #     cmd = (
    #         Header.reference.value
    #         + Header.pj_unit.value
    #         + Commands[command].value[0]
    #         + Footer.close.value
    #     )

    #     msg, success = await self._async_send_command(
    #         cmd,
    #         ack=ACKs[ack.name].value,
    #         command_type=Header.reference.value,
    #     )

    #     if success:
    #         msg = await self._async_replace_headers(msg)

    #     return msg, success

   
    # async def async_get_input_level(self) -> str:
    #     """
    #     Get the current input level
    #     """
    #     state, _ = await self._async_do_reference_op(
    #         "input_level", ACKs.hdmi_ack
    #     )
    #     return InputLevel(state.replace(ACKs.hdmi_ack.value, b"")).name

    # async def _async_get_power_state(self) -> str:
    #     """
    #     Return the current power state

    #     Returns str: values of PowerStates
    #     """
    #     success = False

    #     cmd = (
    #         Header.reference.value
    #         + Header.pj_unit.value
    #         + Commands.power_status.value
    #         + Footer.close.value
    #     )
    #     # try in case we get conn refused
    #     # Try to prevent power state flapping
    #     msg, success = await self._async_send_command(
    #         cmd,
    #         ack=ACKs.power_ack.value,
    #         command_type=Header.reference.value,
    #     )

    #     # Handle error with unexpected acks
    #     if not success:
    #         self.logger.error("Error getting power state: %s", msg)
    #         return success

    #     # remove the headers
    #     state = await self._async_replace_headers(msg)

    #     return PowerStates(state.replace(ACKs.power_ack.value, b"")).name

    # async def async_is_on(self) -> bool:
    #     """
    #     True if the current state is on|reserved
    #     """
    #     pw_status = [PowerStates.on.name]
    #     return await self._async_get_power_state() in pw_status
    
    # async def async_is_ll_on(self) -> bool:
    #     """
    #     True if LL mode is on
    #     """
    #     return await self.async_get_low_latency_state() == LowLatencyModes.on.name

    def print_commands(self) -> str:
        """
        Print out all supported commands
        """
        print_commands = sorted(
            [
                command.name
                for command in Commands
                if command.name not in ["power_status", "current_output", "info"]
            ]
        )
        print("Currently Supported Commands:")
        for command in print_commands:
            print(f"\t{command}")

        print("\n")
        # Print all options
        print("Currently Supported Parameters:")
        from madvr import commands
        import inspect

        for name, obj in inspect.getmembers(commands):
            if inspect.isclass(obj) and obj not in [
                Commands,
                ACKs,
                Footer,
                Enum
            ]:
                print(name)
                for option in obj:
                    print(f"\t{option.name}")
