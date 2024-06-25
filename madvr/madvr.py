"""
Implements the MadVR protocol
"""

import logging
from typing import Final
import asyncio
from madvr.commands import ACKs, Footer, Commands, Enum, Connections
from madvr.errors import AckError, RetryExceededError, HeartBeatError
import os  # For ping functionality
from madvr.wol import send_magic_packet


class Madvr:
    """MadVR Control"""

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        host: str,
        # Can supply a logger object. It can hook into the HA logger
        logger: logging.Logger = logging.getLogger(__name__),
        port: int = 44077,
        mac: str = "",
        connect_timeout: int = 5,
        heartbeat_interval: int = 15,
        ping_interval: int = 5,
    ):
        self.host = host
        self.port = port
        self.mac = mac
        self.connect_timeout: int = connect_timeout
        self.heartbeat_interval: int = heartbeat_interval
        self.ping_interval: int = ping_interval
        self.logger = logger

        # used to indicate if connection is ready
        self.connection_event = asyncio.Event()
        self.stop_reconnect = asyncio.Event()
        self.stop_heartbeat = asyncio.Event()
        self.heartbeat_task = None

        self.lock = asyncio.Lock()

        # track the device state
        self.device_on = False

        # Const values
        self.MADVR_OK: Final = Connections.welcome.value
        self.HEARTBEAT: Final = Connections.heartbeat.value

        # stores all attributes
        self.msg_dict = {}

        # Sockets
        self.reader = None
        self.writer = None

        self.read_limit = 8000
        self.command_read_timeout = 3

        # self.async_write_ha_state from HA
        self.update_callback = None

        # Start the ping task
        self.ping_task = asyncio.create_task(self.ping_until_alive())
        self.powered_off_recently = False
        self.ping_delay_after_power_off: int = 30
        self.logger.debug("Running in debug mode")

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return self.device_on

    def set_update_callback(self, callback):
        """Function to set the callback for updating HA state"""
        self.update_callback = callback

    async def _clear_attr(self) -> None:
        """
        Clear instance attr so HA doesn't report stale values
        """
        # Incoming attrs
        self.msg_dict = {"is_on": False}  # Clear attributes and set 'is_on' to False
        if self.update_callback:
            self.update_callback(self.msg_dict)

    async def close_connection(self) -> None:
        """close the connection"""
        self.logger.debug("closing connection")
        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        except (ConnectionResetError, AttributeError):
            pass
        self.writer = None
        self.reader = None
        self.connection_event.clear()
        self.device_on = False  # update state
        self.msg_dict["is_on"] = self.device_on
        await self._clear_attr()

    async def open_connection(self) -> None:
        """Open a connection"""
        self.logger.debug("Starting open connection")
        try:
            await self._reconnect()
            self.logger.debug("Connection opened")
            if self.heartbeat_task is None or self.heartbeat_task.done():
                self.logger.debug("Starting heartbeat task")
                self.heartbeat_task = asyncio.create_task(self.send_heartbeat())
        except AckError as err:
            self.logger.error(err)

    def connected(self) -> bool:
        """Check if the client is connected."""
        return (
            self.reader is not None
            and self.writer is not None
            and not self.reader.at_eof()
        )

    def stop(self):
        """Stop reconnecting"""
        self.stop_reconnect.set()
        self.stop_heartbeat.set()

        if self.heartbeat_task:
            self.heartbeat_task.cancel()

    async def ping_until_alive(self):
        """Ping the device until it is online then connect to it"""
        while True:
            if self.powered_off_recently:
                self.logger.debug(
                    "Device was recently powered off, waiting for %s seconds",
                    self.ping_delay_after_power_off,
                )
                await asyncio.sleep(self.ping_delay_after_power_off)
                self.powered_off_recently = False

            # if its powered off out of band, this can cause a false positive
            if await self.ping_device():
                # wait a few seconds and confirm the ping
                await asyncio.sleep(2)
                if await self.ping_device():
                    if not self.connected():
                        self.logger.debug("Device is pingable, attempting to connect")
                        await self.open_connection()
            else:
                self.logger.debug(
                    "Device is offline, retrying in %s seconds", self.ping_interval
                )
                # if its marked as connected still, then close the connection
                if self.connected():
                    self.stop()
                    await self.close_connection()
            await asyncio.sleep(self.ping_interval)

    async def _reconnect(self) -> None:
        """
        Initiate keep-alive connection. This should handle any error and reconnect eventually.

        Raises AckError
        """
        if await self.ping_device():
            self.logger.debug("Device is online")
            try:
                self.logger.info("Connecting to Envy: %s:%s", self.host, self.port)

                # Command client
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=5,
                )
                self.logger.debug("Handshaking")
                self.logger.info("Waiting for envy to be available")
                await asyncio.sleep(3)
                await self.send_heartbeat(once=True)
                self.logger.info("Connection established")
                self.connection_event.set()
                self.device_on = True  # update state
                self.msg_dict["is_on"] = self.device_on

            except HeartBeatError:
                self.logger.warning(
                    "Error sending heartbeat, retrying in %s seconds", 2
                )
                await asyncio.sleep(2)
            except TimeoutError:
                self.logger.debug("Connecting timed out")
            except OSError as err:
                self.logger.debug("Connecting failed %s", err)
        else:
            self.logger.debug(
                "Device not responding to ping, retrying in %s seconds",
                self.ping_interval,
            )
            await asyncio.sleep(self.ping_interval)

    async def ping_device(self) -> bool:
        """
        Ping the device to see if it is online
        """
        response = os.system(f"ping -c 1 -W 2 {self.host}")
        return response == 0

    async def send_heartbeat(self, once=False) -> None:
        """
        Send a heartbeat to keep connection open

        You should wrap this in try with OSError and asyncio.TimeoutError exceptions

        Raises HeartBeatError exception
        """
        if once:
            try:
                if not self.connected():
                    self.logger.warning("Connection not established, retrying")
                    await self._reconnect()
                async with self.lock:
                    self.writer.write(self.HEARTBEAT)
                    await self.writer.drain()
                self.logger.debug("heartbeat complete")
            except asyncio.TimeoutError:
                self.logger.error("timeout when sending heartbeat")
            except OSError:
                self.logger.error("error when sending heartbeat")
                await self._reconnect()
            return

        while not self.stop_heartbeat.is_set():
            await self.connection_event.wait()
            try:
                if not self.connected():
                    self.logger.warning("Connection not established, retrying")
                    await self._reconnect()
                async with self.lock:
                    self.writer.write(self.HEARTBEAT)
                    await self.writer.drain()
                self.logger.debug("heartbeat complete")
            except asyncio.TimeoutError as err:
                self.logger.error("timeout when sending heartbeat %s", err)
            except OSError as err:
                self.logger.error("error when sending heartbeat %s", err)
                self.device_on = False  # update state
                self.msg_dict["is_on"] = self.device_on
                if self.ping_task is None or self.ping_task.done():
                    self.ping_task = asyncio.create_task(self.ping_until_alive())
            finally:
                await asyncio.sleep(self.heartbeat_interval)

    async def _construct_command(self, raw_command: list[str]) -> tuple[bytes, str]:
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

        # If len is 1 like ["keypress,val"], then try to split, otherwise its just one word
        # sent directly from HA send_command
        if len(raw_command) == 1:
            try:
                # ['key_press, menu'] -> 'key_press', ['menu']
                # ['activate_profile, SOURCE, 1'] -> 'activate_profile', ['SOURCE', '1']
                command, *raw_value = raw_command[0].split(",")
                # remove space
                values = [val.strip() for val in raw_value]
                self.logger.debug("using command %s and values %s", command, values)
            # if valuerror it means theres just one command like PowerOff, so use that directly
            except ValueError as err:
                self.logger.debug(err)
                command = raw_command[0]
                skip_val = True
        elif len(raw_command) > 3:
            raise NotImplementedError(f"Too many values provided {raw_command}")
        else:
            # else a command was provided as a proper list ['keypress', 'menu']
            # raw command will be a list of 2+
            command, *values = raw_command

        self.logger.debug("checking command %s", command)

        # Check if command is implemented
        if not hasattr(Commands, command):
            raise NotImplementedError(f"Command not implemented: {command}")
        self.logger.debug("Found command")
        # construct the command with nested Enums
        command_name, val, _ = Commands[command].value

        # if there is a value to process
        if not skip_val:
            try:
                # add the base command
                command_base: bytes = command_name

                # append each value with a space
                for value in values:
                    # if value is a number, use it directly
                    if value.isnumeric():  # encode 1 for ActivateProfile
                        command_base += b" " + value.encode("utf-8")
                    else:
                        # else use the enum
                        command_base += b" " + val[value.lstrip(" ")].value

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

    async def send_command(self, command: list) -> str:
        """
        send a given command same as the official madvr ones
        To keep this simple, just send the command without reading response

        command: list - command to send like [KeyPress, MENU]
        Raises RetryExceededError
        """

        # Verify the command is supported
        try:
            cmd, enum_type = await self._construct_command(command)
        except NotImplementedError as err:
            self.logger.warning("command not implemented: %s -- %s", command, err)
            return f"Command not found: {command}"

        self.logger.debug("using values: %s %s", cmd, enum_type)

        # simple retry logic
        retry_count = 0

        while retry_count < 5:
            try:
                if not self.connected():
                    self.logger.warning("Connection not established, retrying")
                    await self._reconnect()
                    retry_count += 1
                    continue
                async with self.lock:
                    self.writer.write(cmd)
                    await self.writer.drain()
                return "ok"  # if success, break the loop
            except ConnectionResetError as err:
                # for now just assuming the envy was turned off
                self.logger.warning(
                    "Connection reset by peer. Assuming envy was turned off manually"
                )
                raise ConnectionResetError("Connection reset by peer") from err
            except (asyncio.TimeoutError, OSError) as err:
                self.logger.debug(
                    "OK receipt timed out or connection failed when reading OK, retrying - %s",
                    err,
                )
                retry_count += 1
                await asyncio.sleep(0.2)  # sleep before retrying
                continue

        raise RetryExceededError("Retry exceeded")

    async def read_notifications(self) -> None:
        """
        Read notifications from the server and update attributes
        """
        while True:
            # wait until the connection is established
            await self.connection_event.wait()
            try:
                msg = await asyncio.wait_for(
                    self.reader.read(self.read_limit), timeout=self.command_read_timeout
                )
                await self._process_notifications(msg.decode("utf-8"))
            except TimeoutError:
                self.logger.debug("No notifications to read")
            except (
                ConnectionResetError,
                AttributeError,
                BrokenPipeError,
                OSError,
            ) as err:
                self.logger.error("Reading notifications failed or timed out: %s", err)
                await self._reconnect()
                continue

            await asyncio.sleep(0.1)
            continue

    async def _process_notifications(self, msg: str) -> None:
        """Parse a message and store the attributes and values in a dictionary"""
        self.logger.debug("Processing notifications: %s", msg)
        notifications = msg.split("\r\n")
        # for each /r/n split it by title, then the rest are values
        for notification in notifications:
            title, *signal_info = notification.split(" ")
            self.logger.debug("Processing notification Title: %s", title)
            # detect if it was turned off out of band
            if "PowerOff" in title:
                self.msg_dict["is_on"] = False
                self.powered_off_recently = True
                self.stop()
                await self.close_connection()

            if "NoSignal" in title:
                self.msg_dict["is_signal"] = False

            # dont process empty values
            if not signal_info:
                continue
            # at least madvr sends attributes in a consistent order
            # could use zip here but why? this works and is simple

            if "IncomingSignalInfo" in title:
                self.msg_dict["is_signal"] = True
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
            elif "MaskingRatio" in title:
                self.msg_dict["masking_res"] = signal_info[0]
                self.msg_dict["masking_dec"] = float(signal_info[1])
                self.msg_dict["masking_int"] = signal_info[2]
            elif "ActivateProfile" in title:
                self.msg_dict["profile_name"] = signal_info[0]
                self.msg_dict["profile_num"] = signal_info[1]
            elif "ActiveProfile" in title:
                self.msg_dict["profile_name"] = signal_info[0]
                self.msg_dict["profile_num"] = signal_info[1]

            # push HA state
            if self.update_callback is not None:
                try:
                    # pass data to HA
                    self.update_callback(self.msg_dict)
                # catch every possible error because python is a mess why can't you just guarantee runtime behavior?
                except Exception as err:  # pylint: disable=broad-except
                    self.logger.error("Error updating HA: %s", err)

    async def power_on(self) -> None:
        """
        Power on the device with a magic packet
        """
        send_magic_packet(self.mac, logger=self.logger)

    async def power_off(self, standby=False) -> str:
        """
        turn off madvr

        standby: bool -> standby instead of poweroff if true
        """
        try:
            # stop trying to reconnect
            self.stop()
            if self.connected():
                res = await self.send_command(["Standby"] if standby else ["PowerOff"])
                return res
        except ConnectionResetError:
            pass
        except RetryExceededError:
            return "Retries Exceeded"
        finally:
            await self.close_connection()
            # set the flag to delay the ping task to avoid race conditions
            self.powered_off_recently = True

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
        print("Currently Supported Parameters:")
        from madvr import commands
        import inspect

        for name, obj in inspect.getmembers(commands):
            if inspect.isclass(obj) and obj not in [Commands, ACKs, Footer, Enum]:
                print(name)
                for option in obj:
                    print(f"\t{option.name}")
