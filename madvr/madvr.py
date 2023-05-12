"""
Implements the MadVR protocol
"""

import logging
from typing import Final, Union
import asyncio
from madvr.commands import ACKs, Footer, Commands, Enum, Connections
from madvr.errors import AckError, RetryExceededError, HeartBeatError


class Madvr:
    """MadVR Control"""

    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        host: str,
        # Can supply a logger object. It can hook into the HA logger
        logger: logging.Logger = logging.getLogger(__name__),
        port: int = 44077,
        connect_timeout: int = 5,
    ):
        self.host = host
        self.port = port
        self.connect_timeout: int = connect_timeout
        self.logger = logger

        # Const values
        self.MADVR_OK: Final = Connections.welcome.value
        self.HEARTBEAT: Final = Connections.heartbeat.value

        # stores all attributes
        self.msg_dict = {}

        # Sockets
        self.reader = None
        self.writer = None
        self.reader_lock = asyncio.Lock()
        self.writer_lock = asyncio.Lock()

        self.is_closed = False
        # Envy does not have an are you on cmd, just assuming its on based on active connection
        self.is_on = False
        self.read_limit = 8000
        self.command_read_timeout = 3

        self.logger.debug("Running in debug mode")

    async def _clear_attr(self) -> None:
        """
        Clear instance attr so HA doesn't report stale values
        """
        # Incoming attrs
        self.msg_dict = {}

    async def close_connection(self) -> None:
        """close the connection"""
        async with self.writer_lock:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except AttributeError:
                # means its already closed
                pass

        self.reader = None
        self.is_closed = True

        # Clear attr
        await self._clear_attr()

    async def open_connection(self) -> None:
        """Open a connection"""
        self.logger.debug("Starting open connection")
        try:
            await self._reconnect()
        except AckError as err:
            self.logger.error(err)

    async def _reconnect(self) -> None:
        """
        Initiate keep-alive connection. This should handle any error and reconnect eventually.

        Raises AckError
        """
        i = 0
        while i < 10:
            try:
                self.logger.info("Connecting to Envy: %s:%s", self.host, self.port)

                # Command client
                async with self.reader_lock:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port),
                        timeout=self.command_read_timeout,
                    )

                # Test heartbeat
                self.logger.debug("Handshaking")

                # Make sure first message says WELCOME
                async with self.reader_lock:
                    msg_envy = await asyncio.wait_for(
                        self.reader.readline(),
                        timeout=10,
                    )

                # Check if first 7 char match
                if self.MADVR_OK != msg_envy[:7]:
                    # This is fatal, and should not retry. If it doesn't respond as expected something is wrong
                    raise AckError(
                        f"Notification did not reply with correct greeting: {msg_envy}"
                    )

                self.logger.info("Waiting for envy to be available")
                # envy needs some time to setup new connections
                await asyncio.sleep(3)

                # handshake func
                await self._send_heartbeat()

                self.logger.info("Connection established")

                self.is_on = True
                self.is_closed = False

                return

            except HeartBeatError:
                self.logger.warning(
                    "Error sending heartbeat, retrying in %s seconds", 2
                )
                await asyncio.sleep(2)
                i += 1
                continue

            # includes conn refused
            # backoff to not spam HA
            except asyncio.TimeoutError:
                self.logger.warning("Connecting timeout, retrying in %s seconds", 2)
                await asyncio.sleep(2)
                i += 1
                continue

            # includes conn refused
            # backoff to not spam HA
            except OSError as err:
                self.logger.warning("Connecting failed, retrying in %s seconds", 2)
                self.logger.debug(err)
                await asyncio.sleep(2)
                i += 1
                continue

    async def _send_heartbeat(self) -> None:
        """
        Send a heartbeat to keep connection open

        You should wrap this in try with OSError and asyncio.TimeoutError exceptions

        Raises HeartBeatError exception
        """
        # confirm can send heartbeat, ready for commands
        self.logger.debug("Sending heartbeats")

        async with self.writer_lock:
            self.writer.write(self.HEARTBEAT)
            await self.writer.drain()

        self.logger.debug("Handshakes complete")

    async def _construct_command(
        self, raw_command: Union[str, list]
    ) -> tuple[bytes, str]:
        """
        Transform commands into their byte values from the string value

        Raises NotImplementedError

        Return:
            bytes: the value to send in bytes
            str: the 'msg' field in the Enum used to filter notifications
        """
        self.logger.debug(
            "raw_command: %s -- raw_command length: %s", raw_command, len(raw_command)
        )

        skip_val = False
        # HA seems to always send commands as a list even if you set them as a str

        # This lets you use single cmds or something with val like KEYPRESS
        # If len is 1, then try to split, otherwise its just one word

        if len(raw_command) == 1:
            try:
                # ['key_press, menu']
                command, raw_value = raw_command[0].split(",")
                # remove space
                value = raw_value.strip()
                self.logger.debug("using command %s and value %s", command, value)
            # if valuerror it means theres just one command like PowerOff, so use that directly
            except ValueError as err:
                self.logger.debug(err)
                self.logger.debug("Using raw_command directly")
                command = raw_command
                skip_val = True
        # if there are more than two values, this is incorrect, error
        elif len(raw_command) > 2:
            self.logger.error(
                "More than two command values provided. Envy does not have more than 2 command values e.g KeyPress MENU"
            )
            raise NotImplementedError(f"Too many values provided {raw_command}")
        else:
            # else a command was provided as a proper list ['keypress', 'menu']
            # raw command will be a list of 2
            command, value = raw_command

        self.logger.debug("using command %s", command)

        # Check if command is implemented
        if not hasattr(Commands, command):
            raise NotImplementedError(f"Command not implemented: {command}")

        # construct the command with nested Enums
        command_name, val, _ = Commands[command].value

        # if there is a value to process
        if not skip_val:
            try:
                command_base: bytes = command_name + b" " + val[value.lstrip(" ")].value
                # Construct command based on required values
                cmd: bytes = command_base + Footer.footer.value
            except KeyError as exc:
                raise NotImplementedError(
                    "Incorrect parameter given for command"
                ) from exc
        else:
            cmd: bytes = command_name + Footer.footer.value

        self.logger.debug("constructed command: %s", cmd)

        return cmd, val

    async def send_command(self, command: Union[str, list]) -> str:
        """
        send a given command same as the official madvr ones
        To keep this simple, just send the command without reading response

        command: str - command to send like KeyPress, MENU
        Raises RetryExceededError
        """

        # Verify the command is supported
        try:
            cmd, enum_type = await self._construct_command(command)
        except NotImplementedError:
            return f"Command not found: {command}"

        self.logger.debug("using values: %s %s", cmd, enum_type)

        # reconnect if client is not init or its off
        if self.reader is None or self.is_on is False:
            # Don't reconnect if poweroff or standby because HA will complain
            if "PowerOff" in command or "Standby" in command:
                return ""
            self.logger.debug("Connection lost - restarting connection")
            await self._reconnect()

        # simple retry logic
        retry_count = 0

        while retry_count < 5:
            # Send the command
            try:
                async with self.writer_lock:
                    self.writer.write(cmd)
                    await self.writer.drain()

            except asyncio.TimeoutError:
                self.logger.debug("OK receipt timed out, retrying")
                retry_count += 1
                continue

            # should catch connection is closed
            except OSError:
                self.logger.warning("connection failed when reading OK, retrying")
                retry_count += 1
                continue

            return ""

        # if we got here something went wrong
        await self.close_connection()
        await self._reconnect()

        return ""

    async def read_notifications(self) -> None:
        """
        Read notifications from the server and update attributes
        """
        # read notifications
        try:
            async with self.reader_lock:
                msg = await asyncio.wait_for(
                    self.reader.read(self.read_limit),
                    timeout=self.command_read_timeout,
                )

        except asyncio.TimeoutError:
            self.logger.warning("Reading notifications timed out")
            return

        except OSError:
            self.logger.warning("Reading notifications failed")
            return

        # if the msg is empty, then the connection is closed
        if not msg:
            # self.logger.warning("Connection closed")
            # await self.close_connection()
            return

        # if the msg is not empty, process it
        await self._process_notifications(msg.decode("utf-8"))

    async def _process_notifications(self, msg: str) -> None:
        """Parse a message and store the attributes and values in a dictionary"""
        self.logger.debug("Processing notifications: %s", msg)
        notifications = msg.split("\r\n")
        # for each /r/n split it by title, then the rest are values
        for notification in notifications:
            title, *signal_info = notification.split(" ")
            # dont process empty values
            if not signal_info:
                continue
            # at least madvr sends attributes in a consistent order
            # could use zip here but why? this works and is simple
            if "IncomingSignalInfo" in title:
                self.msg_dict["incoming_res"] = signal_info[0]
                self.msg_dict["incoming_frame_rate"] = signal_info[1]
                self.msg_dict["incoming_color_space"] = signal_info[3]
                self.msg_dict["incoming_bit_depth"] = signal_info[4]
                self.msg_dict["hdr_flag"] = "HDR" in signal_info[5]
                self.msg_dict["incoming_colorimetry"] = signal_info[6]
                self.msg_dict["incoming_black_levels"] = signal_info[7]
                self.msg_dict["incoming_aspect_ratio"] = signal_info[8]
            elif "OutgoingSignalInfo" in title:
                self.msg_dict["outgoing_res"] = signal_info[0]
                self.msg_dict["outgoing_frame_rate"] = signal_info[1]
                self.msg_dict["outgoing_color_space"] = signal_info[3]
                self.msg_dict["outgoing_bit_depth"] = signal_info[4]
                self.msg_dict["outgoing_hdr_flag"] = "HDR" in signal_info[5]
                self.msg_dict["outgoing_colorimetry"] = signal_info[6]
                self.msg_dict["outgoing_black_levels"] = signal_info[7]
            elif "AspectRatio" in title:
                self.msg_dict["aspect_res"] = signal_info[0]
                self.msg_dict["aspect_dec"] = float(signal_info[1])
                self.msg_dict["aspect_int"] = signal_info[2]
                self.msg_dict["aspect_name"] = signal_info[3]

    async def power_off(self, standby=False) -> str:
        """
        turn off madvr it must have a render thread active at the moment
        once it is off, you can't turn it back on unless standby=True
        It uses about 30w idle on standby. I use IR via harmony to turn it on

        standby: bool -> standby instead of poweroff if true
        """
        # dont do anything if its off besides mark it off
        # sending command will open connection
        try:
            res = await self.send_command("Standby" if standby else "PowerOff")
            await self.close_connection()
            self.is_on = False

            return res

        except RetryExceededError:
            return "Retries Exceeded"

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
            if inspect.isclass(obj) and obj not in [Commands, ACKs, Footer, Enum]:
                print(name)
                for option in obj:
                    print(f"\t{option.name}")
