"""
Implements the MadVR protocol
"""

import logging
from typing import Final, Union
import re
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

        # Incoming attrs
        self.incoming_res = ""
        self.incoming_frame_rate = ""
        self.incoming_color_space = ""
        self.incoming_bit_depth = ""
        self.hdr_flag = False
        self.incoming_colorimetry = ""
        self.incoming_black_levels = ""
        self.incoming_aspect_ratio = ""
        self.aspect_ratio: float = 0

        # Temps
        self.temp_gpu: int = 0
        self.temp_hdmi: int = 0
        self.temp_cpu: int = 0
        self.temp_mainboard: int = 0

        # Outgoing signal
        self.outgoing_res = ""
        self.outgoing_frame_rate = ""
        self.outgoing_color_space = ""
        self.outgoing_bit_depth = ""
        self.outgoing_colorimetry = ""
        self.outgoing_hdr_flag = False
        self.outgoing_black_levels = ""

        # Sockets
        self.reader = None
        self.writer = None
        self.reader_lock = asyncio.Lock()
        self.writer_lock = asyncio.Lock()

        self.notification_reader = None
        self.notification_writer = None
        self.notification_reader_lock = asyncio.Lock()
        self.notification_writer_lock = asyncio.Lock()
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
        self.incoming_res = ""
        self.incoming_frame_rate = ""
        self.incoming_color_space = ""
        self.incoming_bit_depth = ""
        self.hdr_flag = False
        self.incoming_colorimetry = ""
        self.incoming_black_levels = ""
        self.incoming_aspect_ratio = ""
        self.aspect_ratio = 0

        # Temps
        self.temp_gpu = 0
        self.temp_hdmi = 0
        self.temp_cpu = 0
        self.temp_mainboard = 0

        # Outgoing signal
        self.outgoing_res = ""
        self.outgoing_frame_rate = ""
        self.outgoing_color_space = ""
        self.outgoing_bit_depth = ""
        self.outgoing_colorimetry = ""
        self.outgoing_hdr_flag = False
        self.outgoing_black_levels = ""

    async def close_connection(self) -> None:
        """close the connection"""
        async with self.writer_lock:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except AttributeError:
                # means its already closed
                pass
        async with self.notification_writer_lock:
            try:
                self.notification_writer.close()
                await self.notification_writer.wait_closed()
            except AttributeError:
                # means its already closed
                pass

        self.reader = None
        self.notification_reader = None

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

        while True:
            try:
                self.logger.info("Connecting to Envy: %s:%s", self.host, self.port)

                # Command client
                async with self.reader_lock, self.notification_reader_lock:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port),
                        timeout=self.command_read_timeout,
                    )

                    # Notifications client
                    (
                        self.notification_reader,
                        self.notification_writer,
                    ) = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port), timeout=20
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

                # Make sure first message says WELCOME for notifications
                async with self.notification_reader_lock:
                    msg_envy = await asyncio.wait_for(
                        self.notification_reader.readline(), timeout=20
                    )

                # Check if first 7 char match
                if self.MADVR_OK != msg_envy[:7]:
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
                continue

            # includes conn refused
            # backoff to not spam HA
            except asyncio.TimeoutError:
                self.logger.warning("Connecting timeout, retrying in %s seconds", 2)
                await asyncio.sleep(2)
                continue

            # includes conn refused
            # backoff to not spam HA
            except OSError as err:
                self.logger.warning("Connecting failed, retrying in %s seconds", 2)
                self.logger.debug(err)
                await asyncio.sleep(2)
                continue

    async def _send_heartbeat(self) -> None:
        """
        Send a heartbeat to keep connection open

        You should wrap this in try with OSError and asyncio.TimeoutError exceptions

        Raises HeartBeatError exception
        """
        i = 0

        while i < 3:
            # confirm can send heartbeat, ready for commands
            self.logger.debug("Sending heartbeats")

            async with self.writer_lock:
                self.writer.write(self.HEARTBEAT)
                await self.writer.drain()

            # Recv until we find ok or timeout
            if not await self._read_until_ok(self.reader):
                i += 1
                continue

            # send heartbeat with notification and read ack and then regular client
            # ensure both work one after the next
            async with self.notification_writer_lock:
                self.notification_writer.write(self.HEARTBEAT)
                await self.notification_writer.drain()

            if not await self._read_until_ok(self.notification_reader):
                i += 1
                continue

            self.logger.debug("Handshakes complete")

            return

        raise HeartBeatError("Sending heartbeat fatal error")

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

    async def _read_until_ok(self, client: asyncio.StreamReader) -> bool:
        """
        Read the buffer until we get ok or timeout because a timeout means no more to read
        """
        counter = 0
        # exit loop if exceed maximum checks for ok or retries
        while True:
            try:
                async with self.reader_lock, self.notification_reader_lock:
                    data = await asyncio.wait_for(client.readline(), timeout=10)
                    self.logger.debug("_read_until_ok: data found: %s", data)

                if ACKs.reply.value not in data:
                    self.logger.debug("OK not found yet counter: %s", counter)
                    counter += 1
                    continue

                self.logger.debug("OK found counter: %s", counter)
                return True

            except asyncio.TimeoutError:
                self.logger.debug("Timeout reading ack with counter: %s", counter)
                return False

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

    async def start_read_notifications(self, wait_forever: bool) -> None:
        """
        Listen for notifications. Meant to run as a background task
        wait_forever: bool -> if true, it will block forever. False useful for testing
        """

        # Receive data in a loop
        i = 0
        while wait_forever or i < 5:
            # TODO: stop loop if remote is off, start when remote is on
            if self.is_on is False:
                self.logger.debug("envy is off")
                asyncio.sleep(5)
                continue

            if self.notification_reader is None:
                self.logger.debug("notifications waiting for connection to open")
                asyncio.sleep(2)
                continue

            try:
                # send hearbeat
                async with self.notification_writer_lock:
                    self.notification_writer.write(self.HEARTBEAT)
                    await self.notification_writer.drain()

                async with self.notification_reader_lock:
                    data = await asyncio.wait_for(
                        self.reader.readline(),
                        timeout=self.command_read_timeout,
                    )

                asyncio.sleep(1)

                i += 1

                if data:
                    # process data which will get added as class attr
                    await self._process_notifications(data)
                else:
                    # just wait forever for data
                    # send heartbeat keep conn open
                    async with self.notification_writer_lock:
                        self.notification_writer.write(self.HEARTBEAT)
                        await self.notification_writer.drain()
                    continue
            except asyncio.TimeoutError:
                self.logger.debug("Connection timed out")
                async with self.notification_writer_lock:
                    self.notification_writer.write(self.HEARTBEAT)
                    await self.notification_writer.drain()
                continue
            except OSError:
                self.logger.debug("Connection error")
                async with self.notification_writer_lock:
                    self.notification_writer.write(self.HEARTBEAT)
                    await self.notification_writer.drain()
                continue
            except AttributeError:
                await self._reconnect()

    async def _process_notifications(self, input_data: Union[bytes, str]) -> None:
        """
        Process arbitrary stream of notifications and set them as instance attr
        """
        # This code constructs a dict for all values processed
        self.logger.debug("Processing data for %s", input_data)
        try:
            if isinstance(input_data, bytes):
                # This pattern will be able to extract from the byte encoded stream
                pattern = r"([A-Z][^\r\n]*)\r\n"
                groups = re.findall(pattern, input_data.decode())
                # split the groups, the first element is the key, remove the key from the values
                # for each match in groups, add it to dict
                # {"key": ["val1", "val2"]}
                val_dict: dict = {
                    group.split()[0]: group.replace(group.split()[0] + " ", "").split()
                    for group in groups
                }
                self.logger.debug("groups: %s", groups)
            else:
                self.logger.debug("input data: %s", input_data)
                # This pattern extracts from a regular string
                # If we have a str its assumed we are dealing with one output stream
                pattern = r"([A-Z][A-Za-z]*)\s(.*)"
                match = re.search(pattern, input_data)
                val_dict: dict = {match.group(1): match.group(2).split()}

            self.logger.debug("val dict: %s", val_dict)
        except AttributeError:
            return

        # Map values to attr
        incoming_signal_info: list = val_dict.get("IncomingSignalInfo", [])
        if incoming_signal_info:
            self.logger.debug("incoming signal detected: %s", incoming_signal_info)
            self.incoming_res = incoming_signal_info[0]
            self.incoming_frame_rate = incoming_signal_info[1]
            self.incoming_color_space = incoming_signal_info[3]
            self.incoming_bit_depth = incoming_signal_info[4]
            self.hdr_flag = "HDR" in incoming_signal_info[5]
            self.incoming_colorimetry = incoming_signal_info[6]
            self.incoming_black_levels = incoming_signal_info[7]
            self.incoming_aspect_ratio = incoming_signal_info[8]

        aspect_ratio: list = val_dict.get("AspectRatio", [])
        if aspect_ratio:
            self.logger.debug("incoming AR detected: %s", aspect_ratio)
            self.aspect_ratio = float(aspect_ratio[1])

        get_temps: list = val_dict.get("Temperatures", [])
        if get_temps:
            self.logger.debug("incoming Temps detected: %s", get_temps)
            self.temp_gpu = int(get_temps[0])
            self.temp_hdmi = int(get_temps[1])
            self.temp_cpu = int(get_temps[2])
            self.temp_mainboard = int(get_temps[3])

        outgoing_signal_info: list = val_dict.get("OutgoingSignalInfo", [])
        if outgoing_signal_info:
            self.logger.debug("outgoing signal detected: %s", outgoing_signal_info)
            self.outgoing_res = outgoing_signal_info[0]
            self.outgoing_frame_rate = outgoing_signal_info[1]
            self.outgoing_color_space = outgoing_signal_info[3]
            self.outgoing_bit_depth = outgoing_signal_info[4]
            self.outgoing_hdr_flag = "HDR" in outgoing_signal_info[5]
            self.outgoing_colorimetry = outgoing_signal_info[6]
            self.outgoing_black_levels = outgoing_signal_info[7]

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
