"""
Implements the MadVR protocol
"""

import logging
from typing import Final
import re
import time
import socket
from madvr.commands import ACKs, Footer, Commands, Enum, Connections
from madvr.errors import AckError, RetryExceededError


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

        # Const values
        self.MADVR_OK: Final = Connections.welcome.value
        self.HEARTBEAT: Final = Connections.heartbeat.value

        # Incoming attrs
        # TODO add tehse to HA
        self.incoming_res = ""
        self.incoming_frame_rate = ""
        self.incoming_color_space = ""
        self.incoming_bit_depth = ""
        self.hdr_flag = False
        self.incoming_colorimetry = ""
        self.incoming_black_levels = ""
        self.incoming_aspect_ratio = ""
        # TODO: use this to determine masking in HA
        # TODO convert to float?
        self.aspect_ratio: float = 0

        # Sockets
        self.client = None
        self.notification_client = None
        self.is_closed = False
        self.read_limit = 8000
        self.command_read_timeout = 3
        self.logger.debug("Running in debug mode")

    def close_connection(self) -> None:
        """close the connection"""
        # TODO: HA should close client on shutdown
        self.client.close()
        self.notification_client.close()
        self.is_closed = True

    def open_connection(self) -> None:
        """Open a connection"""
        self.logger.debug("Starting open connection")

        try:
            self.reconnect()
        except AckError as err:
            self.logger.error(err)

    def reconnect(self) -> None:
        """
        Initiate keep-alive connection. This should handle any error and reconnect eventually.
        
        Raises AckError
        """
        while True:
            try:
                self.logger.info("Connecting to Envy: %s:%s", self.host, self.port)
                # Commands
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.connect((self.host, self.port))
                self.client.settimeout(10)

                # Notifications
                self.notification_client = socket.socket(
                    socket.AF_INET, socket.SOCK_STREAM
                )
                self.notification_client.settimeout(20)
                self.notification_client.connect((self.host, self.port))

                self.logger.info("Connected to Envy")

                # Test heartbeat
                self.logger.debug("Handshaking")

                # Make sure first message says WELCOME
                msg_envy = self.client.recv(self.read_limit)

                # Check if first 7 char match
                if self.MADVR_OK != msg_envy[:7]:
                    raise AckError(
                        f"Notification did not reply with correct greeting: {msg_envy}"
                    )

                # Make sure first message says WELCOME for notifications
                msg_envy = self.notification_client.recv(self.read_limit)

                # Check if first 7 char match
                if self.MADVR_OK != msg_envy[:7]:
                    raise AckError(
                        f"Notification did not reply with correct greeting: {msg_envy}"
                    )

                # envy needs some time to setup new connections
                time.sleep(3)

                # confirm can send heartbeat, ready for commands
                self.logger.debug("Sending heartbeats")
                self.client.send(self.HEARTBEAT)

                # read first 4 bytes for ok\r\n
                ack_reply = self.client.recv(4)

                if ack_reply != ACKs.reply.value:
                    raise AckError(f"{ack_reply} does not match {ACKs.reply.value}")

                # send heartbeat with notification and read ack and then regular client
                # ensure both work one after the next
                self.notification_client.send(self.HEARTBEAT)

                # read first 4 bytes for ok\r\n
                ack_reply = self.notification_client.recv(4)

                if ack_reply != ACKs.reply.value:
                    raise AckError(f"{ack_reply} does not match {ACKs.reply.value}")

                # send again on regular client to make sure both clients work
                self.client.send(self.HEARTBEAT)

                # read first 4 bytes for ok\r\n
                ack_reply = self.client.recv(4)

                if ack_reply != ACKs.reply.value:
                    raise AckError(f"{ack_reply} does not match {ACKs.reply.value}")

                self.logger.debug("Handshakes complete")

                return

            # includes conn refused
            except socket.timeout:
                self.logger.warning("Connection timed out, retrying in 2 seconds")
                time.sleep(2)
            except OSError as err:
                self.logger.warning("Connecting failed, retrying in 2 seconds")
                self.logger.debug(err)
                time.sleep(2)

    def read_notifications(self, wait_forever: bool) -> None:
        """
        Listen for notifications
        wait_forever: bool -> if true, it will block forever. False useful for testing
        """
        # TODO: should this be a second integration?
        # Is there a way for HA to always poll in background?z
        # Receive data in a loop

        i = 0
        while wait_forever or i < 5:
            try:
                self.notification_client.sendall(self.HEARTBEAT)
                data = self.notification_client.recv(self.read_limit)
                time.sleep(1)
                i += 1
                if data:
                    # process data which will get added as class attr
                    self._process_notifications(data)
                else:
                    # just wait forever for data
                    # send heartbeat keep conn open
                    self.notification_client.sendall(self.HEARTBEAT)
                    continue
            except socket.timeout:
                self.logger.debug("Connection timed out")
                self.notification_client.sendall(self.HEARTBEAT)
                continue
            except socket.error:
                self.logger.debug("Connection error")
                self.notification_client.sendall(self.HEARTBEAT)
                continue

    def _construct_command(self, raw_command: str) -> tuple[bytes, bool, str]:
        """
        Transform commands into their byte values from the string value

        Raises NotImplementedError

        Return:
            bytes: the value to send in bytes
            bool: if its informational
            str: the 'msg' field in the Enum used to filter notifications
        """
        # split command into the base and the action like menu: left
        self.logger.debug("raw_command: %s", raw_command)
        skip_val = False
        
        # This lets you use single cmds or something with val like KEYPRESS
        try:
            # key_press, menu
            command, raw_value = raw_command.split(",")
            value = raw_value.strip()
            self.logger.debug("using command %s", command)
            self.logger.debug("using value %s", value)
        except ValueError:
            self.logger.debug("Not able to split command")
            command = raw_command
            skip_val = True
            self.logger.debug("using command %s", command)

        # Check if command is implemented
        if not hasattr(Commands, command):
            raise NotImplementedError(f"Command not implemented: {command}")

        # construct the command with nested Enums
        command_name, val, is_info = Commands[command].value
        if not skip_val:
            # self.logger.debug("command_name: %s", command_name)
            # self.logger.debug("val: %s", val[value.lstrip(" ")].value)
            # self.logger.debug("is info: %s", is_info.value)
            try:
                command_base: bytes = command_name + b" " + val[value.lstrip(" ")].value
                # Construct command based on required values
                cmd: bytes = command_base + Footer.footer.value
            except KeyError as exc:
                raise NotImplementedError("Incorrect parameter given for command") from exc
        else:
            cmd: bytes = command_name + Footer.footer.value

        self.logger.debug("constructed command: %s", cmd)

        return cmd, is_info.value, val

    def send_command(self, command: str) -> str:
        """
        send a given command same as the official madvr ones

        command: str - command to send like KeyPress, MENU
        Raises RetryExceededError
        """

        try:
            cmd, is_info, enum_type = self._construct_command(command)
        except NotImplementedError:
            return "Command not found"

        # simple retry logic
        retry_count = 0

        # reconnect if client is not init
        if self.client is None:
            self.logger.debug("Reforming connection")
            self.reconnect()

        while retry_count < 5:
            # Send the command
            self.client.send(cmd)

            # read ack which should be ok
            try:
                ack_reply = self.client.recv(self.read_limit)

                # envy can send anything at any time, not very robust API
                # see if OK is contained in what we read
                if ACKs.reply.value not in ack_reply:
                    self.logger.debug("ACK not found in reply: %s", ack_reply)
                    self.logger.debug("retrying")
                    retry_count += 1
                    continue

            except socket.timeout:
                self.logger.error("Ack receipt timed out, retrying")
                retry_count += 1
                continue

            try:
                # If its an info, get the rest of the info
                if is_info:
                    # read response
                    res = self.client.recv(self.read_limit)
                    self.logger.debug("Response from info: %s", res)

                    # process the output
                    return self._process_info(res, enum_type["msg"].value)

            except socket.timeout:
                self.logger.error("Ack receipt timed out, retrying")
                retry_count += 1
                continue

            return

        raise RetryExceededError("Retry count exceeded")


    def _process_notifications(self, input_data: bytes) -> None:
        """
        Process arbitrary stream of notifications and set them as class attr
        """
        pattern = r"([A-Z][^\r\n]*)\r\n"
        groups = re.findall(pattern, input_data.decode())

        # split the groups, the first element is the key, remove the key from the values
        # for each match in groups, add it to dict
        # {"key": ["val1", "val2"]}
        val_dict: dict = {
            group.split()[0]: group.replace(group.split()[0] + " ", "").split()
            for group in groups
        }

        incoming_signal_info: list = val_dict.get("IncomingSignalInfo", [])
        if incoming_signal_info:
            self.logger.debug(incoming_signal_info)
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
            self.logger.debug(aspect_ratio)
            self.aspect_ratio = aspect_ratio[1]

        # TODO: add the rest of notifications

    # TODO: poll envy for HDR info
    # TODO: for HA, poll every 1s
    # TODO: poll SDR in HA as well, basically whatevre the fvalue is
    # use automation to see when the state changes
    def poll_hdr(self) -> bool:
        """
        Poll envy if HDR is being processed
        This is needed because HDR flag is broken with JVC NZ, if not others
        """
        # simple lookup for now

        # TODO: process into self attributes?
        return "HDR" in self.send_command("get_incoming_signal_info")

    def poll_aspect_ratio(self) -> float:
        """Poll envy for aspect ratio"""
        # TODO This should use spectRatio  info?

    def _process_info(self, input_data: bytes, filter_str: str) -> list:
        """
        Process info given input and a filter str
        """
        # AspectRatio
        # IncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9

        lines = input_data.decode().split("\r\n")
        for line in lines:
            if filter_str in line:
                return line.replace(filter_str + " ", "")

    def _process_temperatures(self, temp_string: bytes) -> list:
        """
        Process the temp stuff
        """
        # look for things between "Temperature" and \r, using word boundaries
        # TODO: construct a dict of each kind of sensor, or add as internal state?
        # %gpu% %hdmiInput% “%cpu%” “%mainboard
        return re.findall(r"\b\d+\b", temp_string.decode())

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
