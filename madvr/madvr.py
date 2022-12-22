"""
Implements the MadVR protocol
"""

import logging
from typing import Final
import time
import socket
from madvr.commands import ACKs, Footer, Commands, Enum, Connections

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
        self.client = None
        self.is_closed = False
        self.read_limit = 8000
        self.command_read_timeout = 3
        self.logger.debug("Running in debug mode")

    def close_connection(self):
        """close the connection"""
        self.client.close()
        self.is_closed = True
    
    def open_connection(self) -> bool:
        """Open a connection"""
        self.logger.debug("Starting open connection")
        msg, success = self.reconnect()

        if not success:
            self.logger.error(msg)

        return success

    def reconnect(self):
        """Initiate keep-alive connection. This should handle any error and reconnect eventually."""
        while True:
            try:
                self.logger.info(
                    "Connecting to Envy: %s:%s", self.host, self.port
                )
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.settimeout(10)
                
                self.client.connect((self.host, self.port))
                self.logger.info("Connected to Envy")

                # Test heartbeat
                self.logger.debug("Handshaking")

                # Make sure first message says WELCOME
                msg_envy = self.client.recv(self.read_limit)
                self.logger.debug(self.MADVR_OK)
                self.logger.debug(msg_envy)

                # Check if first 7 char match
                if self.MADVR_OK != msg_envy[:7]:
                    result = f"Envy did not reply with correct greeting: {msg_envy}"
                    self.logger.error(result)
                    return result, False
                
                # envy needs some time to setup new connection
                time.sleep(3)

                # confirm can send heartbeat, ready for commands
                self.logger.debug("Sending heartbeat")
                self.client.send(self.HEARTBEAT)
                
                # read first 4 bytes for ok\r\n
                ack_reply = self.client.recv(4)
                self.logger.debug(ack_reply)

                if ack_reply != ACKs.reply.value:
                    return "Ack OK not received", False

                self.logger.debug("Handshake complete and we are connected")
                return "Connection done", True

            # includes conn refused
            except socket.timeout:
                self.logger.warning("Connection timed out, retrying in 2 seconds")
                time.sleep(2)
            except OSError as err:
                self.logger.warning("Connecting failed, retrying in 2 seconds")
                self.logger.debug(err)
                time.sleep(2)

    def _construct_command(
        self, raw_command: str
    ) -> tuple[bytes, bool]:
        """
        Transform commands into their byte values from the string value
        """
        # split command into the base and the action like menu: left
        self.logger.debug(raw_command)
        skip_val = False
        try:
            # key_press, menu
            command, value = raw_command.split(",")
        except ValueError:
            command = raw_command
            skip_val = True

        self.logger.debug(command)
        # Check if command is implemented
        if not hasattr(Commands, command):
            self.logger.error("Command not implemented: %s", command)
            return b"", None

        # construct the command with nested Enums
        command_name, val, is_info = Commands[command].value
        if not skip_val:
            self.logger.debug("command_name: %s", command_name)
            self.logger.debug("val: %s", val[value.lstrip(" ")].value)
            self.logger.debug("is info: %s", is_info.value)
            command_base: bytes = command_name + b" " + val[value.lstrip(" ")].value
            # Construct command based on required values
            command: bytes = (
                command_base + Footer.footer.value
            )
        else:
            command: bytes = (
                command + Footer.footer.value
            )
        self.logger.debug("command: %s", command)

        return command, is_info.value

    def send_command(self, command: str) -> str:
        """send a given command"""

        cmd, is_info = self._construct_command(command)
        if cmd is False:
            return "Command not found"

        self.logger.debug("Sending command: %s", cmd)
        self.logger.debug("Is informational %s", is_info)

        # Send the command
        self.client.send(cmd)

        # read ack which should be ok
        ack_reply = self.client.recv(self.read_limit)
        self.logger.debug(ack_reply)
        if ack_reply != ACKs.reply.value:
            self.logger.error(ack_reply)
            return "Ack OK not received when sending command", False

        if is_info:
            # TODO: check if the response matches stuff in Notifications
            # read response
            res = self.client.recv(self.read_limit)
            self.logger.debug(res)
            return res

        return "ok"

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
