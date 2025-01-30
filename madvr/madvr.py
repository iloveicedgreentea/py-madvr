"""
Implements the MadVR protocol
"""

import asyncio
import logging
from typing import Any, Coroutine, Final, Iterable

from madvr.commands import Commands, Connections, Footer
from madvr.consts import (
    COMMAND_TIMEOUT,
    CONNECT_TIMEOUT,
    DEFAULT_PORT,
    HEARTBEAT_INTERVAL,
    PING_DELAY,
    PING_INTERVAL,
    READ_LIMIT,
    REFRESH_TIME,
    SMALL_DELAY,
    TASK_CPU_DELAY,
)
from madvr.errors import AckError, HeartBeatError
from madvr.notifications import NotificationProcessor
from madvr.wol import send_magic_packet


class Madvr:
    """MadVR Control"""

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        host: str,
        # Can supply a logger object. It can hook into the HA logger
        logger: logging.Logger = logging.getLogger(__name__),
        port: int = DEFAULT_PORT,
        # if blank, it will request it from the device for WOL
        mac: str = "",
        connect_timeout: int = CONNECT_TIMEOUT,
        heartbeat_interval: int = HEARTBEAT_INTERVAL,
        ping_interval: int = PING_INTERVAL,
        # pass in the hass loop
        loop: asyncio.AbstractEventLoop | None = None,
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
        self.stop_heartbeat = asyncio.Event()

        # command queue to store commands as they come in
        self.command_queue: asyncio.Queue = asyncio.Queue()
        self.stop_commands_flag = asyncio.Event()

        # background tasks
        self.tasks: list[asyncio.Task] = []
        self.loop = loop

        self.lock = asyncio.Lock()

        # Const values
        self.MADVR_OK: Final = Connections.welcome.value
        self.HEARTBEAT: Final = Connections.heartbeat.value

        # stores all attributes
        self.msg_dict: dict = {}

        # Sockets
        self.reader = None
        self.writer = None

        self.read_limit: int = READ_LIMIT
        self.command_read_timeout: int = COMMAND_TIMEOUT

        # self.async_write_ha_state from HA
        self.update_callback: Any = None

        self.notification_processor = NotificationProcessor(self.logger)
        self.powered_off_recently: bool = False
        self.ping_delay_after_power_off: int = PING_DELAY
        self.logger.debug("Running in debug mode")

    ##########################
    # Props
    ##########################
    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return self.msg_dict.get("is_on", False)

    @property
    def mac_address(self) -> str:
        """Return the mac address of the device."""
        return self.msg_dict.get("mac_address", "")

    def set_update_callback(self, callback: Any) -> None:
        """Function to set the callback for updating HA state"""
        self.update_callback = callback

    async def async_add_tasks(self) -> None:
        """Add background tasks with error handling."""
        if not self.loop:
            self.loop = asyncio.get_event_loop()

        async def wrapped_task(coro: Coroutine[Any, Any, Any], name: str) -> None:
            """Wrapper to handle task errors."""
            try:
                await coro
            except asyncio.CancelledError:
                self.logger.debug("Task %s was cancelled", name)
            except Exception as e:
                self.logger.exception("Task %s failed with error: %s", name, e)
                # If a critical task fails, trigger reconnection
                if name in ["notifications", "heartbeat"]:
                    await self._handle_power_off()

        task_definitions = [
            (self.task_handle_queue(), "queue"),
            (self.task_read_notifications(), "notifications"),
            (self.send_heartbeat(), "heartbeat"),
            (self.task_ping_until_alive(), "ping"),
            (self.task_refresh_info(), "refresh"),
        ]

        # start tasks in wrapper
        for coro, name in task_definitions:
            task = self.loop.create_task(wrapped_task(coro, name))
            task.set_name(name)  # Set task name for identification
            self.tasks.append(task)

    async def async_cancel_tasks(self) -> None:
        """Cancel all tasks except ping unless final shutdown."""
        non_ping_tasks = []

        # Separate ping task from other tasks
        for task in self.tasks:
            if task.get_name() == "ping":
                continue

            non_ping_tasks.append(task)
            if not task.done():
                task.cancel()

        # Wait for non-ping tasks to cancel
        if non_ping_tasks:
            await asyncio.gather(*non_ping_tasks, return_exceptions=True)

        # Clear task list but preserve ping task if not shutting down
        self.tasks.clear()

    ##########################
    # Background tasks
    ##########################
    async def task_handle_queue(self) -> None:
        """Handle command queue."""
        while True:
            await self.connection_event.wait()
            while (
                not self.command_queue.empty() and not self.stop_commands_flag.is_set()
            ):
                command = await self.command_queue.get()
                self.logger.debug("sending queue command %s", command)
                try:
                    await self.send_command(command)
                except NotImplementedError as err:
                    self.logger.warning("Command not implemented: %s", err)
                except (
                    ConnectionError,
                    ConnectionResetError,
                    BrokenPipeError,
                    OSError,
                ) as err:
                    self.logger.warning(
                        "Connection error while sending command: %s", err
                    )
                    # Put the command back in the queue unless it's a power command
                    if not any(cmd in ["PowerOff", "Standby"] for cmd in command):
                        await self.command_queue.put(command)
                    await self._handle_power_off()
                    break  # Exit the inner loop to wait for reconnection
                except Exception as err:
                    self.logger.error("Unexpected error when sending command: %s", err)

            if self.stop_commands_flag.is_set():
                self.clear_queue()
                self.logger.debug("Stopped processing commands")
                break

            await asyncio.sleep(TASK_CPU_DELAY)

    async def task_read_notifications(self) -> None:
        """
        Read notifications from the server and update attributes.
        The task maintains connection state and processes notifications continuously.
        """
        while True:
            # Wait for connection to be established
            await self.connection_event.wait()

            try:
                if not self.reader:
                    self.logger.warning("Reader not available")
                    await self._set_connected(False)
                    await asyncio.sleep(TASK_CPU_DELAY)
                    continue

                msg = await asyncio.wait_for(
                    self.reader.read(self.read_limit),
                    timeout=self.command_read_timeout,
                )

                # An empty message is probably fine
                if not msg:
                    self.logger.debug("Empty message received")
                    continue

                try:
                    await self._process_notifications(msg.decode("utf-8"))
                except UnicodeDecodeError as e:
                    self.logger.error("Failed to decode message: %s", e)
                    continue

            except asyncio.TimeoutError:
                # This is normal - no notifications to read
                await asyncio.sleep(TASK_CPU_DELAY)
                continue

            except (ConnectionResetError, BrokenPipeError) as err:
                self.logger.error("Connection error in notification task: %s", err)
                # Connection was reset - mark as disconnected and trigger reconnect after
                await self._handle_power_off()
                continue

            except Exception as e:
                self.logger.exception("Unexpected error in notification task: %s", e)
                await asyncio.sleep(TASK_CPU_DELAY)
                continue

            await asyncio.sleep(TASK_CPU_DELAY)

    async def send_heartbeat(self, once: bool = False) -> None:
        """
        Send a heartbeat to keep connection open.
        Args:
            once: If True, only send one heartbeat instead of continuous
        """

        async def perform_heartbeat() -> None:
            if not self.connected or not self.writer:
                raise HeartBeatError("Connection not established")

            try:
                async with self.lock:
                    if self.writer:
                        self.writer.write(self.HEARTBEAT)
                        await self.writer.drain()
                        self.logger.debug("Heartbeat sent")
            except (ConnectionError, OSError) as err:
                raise HeartBeatError(f"Failed to send heartbeat: {err}") from err

        if once:
            await perform_heartbeat()
            return

        while not self.stop_heartbeat.is_set():
            await self.connection_event.wait()

            try:
                await perform_heartbeat()
            except HeartBeatError as err:
                self.logger.error("Heartbeat error: %s", err)
                await self._handle_power_off()
                # Don't retry immediately after error
                await asyncio.sleep(self.heartbeat_interval * 2)
                continue

            await asyncio.sleep(self.heartbeat_interval)

    async def task_ping_until_alive(self) -> None:
        """Check if the device is connectable and connect to it on success."""
        consecutive_failures = 0
        MAX_FAILURES = 3

        while True:
            try:
                # this will induce flapping otherwise
                if self.powered_off_recently:
                    self.logger.debug(
                        "Device was recently powered off, waiting for %s seconds",
                        self.ping_delay_after_power_off,
                    )
                    await asyncio.sleep(self.ping_delay_after_power_off)
                    # reset the flag
                    self.powered_off_recently = False

                is_connectable = await self.is_device_connectable()

                if is_connectable:
                    consecutive_failures = 0  # Reset failure counter on success
                    # Double-check connectivity after a short delay
                    await asyncio.sleep(SMALL_DELAY)
                    is_connectable = await self.is_device_connectable()

                    if is_connectable and not self.connected:
                        self.logger.debug(
                            "Device is connectable, attempting to connect"
                        )
                        try:
                            await self.open_connection()
                        except ConnectionError as err:
                            self.logger.error(
                                "Error opening connection after connectivity check: %s",
                                err,
                            )
                            consecutive_failures += 1
                else:
                    self.logger.debug(
                        "Device is not connectable, retrying in %s seconds",
                        self.ping_interval,
                    )
                    # if its not connectable but we are "connected", then the device was turned off
                    if self.connected:
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_FAILURES:
                            self.logger.warning(
                                "Multiple consecutive connection failures, forcing reconnect"
                            )
                            await self._handle_power_off()
                            consecutive_failures = 0

                await asyncio.sleep(self.ping_interval)

            except Exception as err:
                self.logger.exception("Unexpected error in ping task: %s", err)
                # Don't let errors kill the ping task
                await asyncio.sleep(self.ping_interval)

    async def task_refresh_info(self) -> None:
        """Task to refresh some device info every 20s"""
        while True:
            # wait until the connection is established
            await self.connection_event.wait()
            cmds = [
                ["GetMacAddress"],
                ["GetTemperatures"],
                # get signal info in case a change was missed and its sitting in limbo
                ["GetIncomingSignalInfo"],
                ["GetOutgoingSignalInfo"],
                ["GetAspectRatio"],
                ["GetMaskingRatio"],
            ]
            for cmd in cmds:
                await self.add_command_to_queue(cmd)
            await asyncio.sleep(REFRESH_TIME)

    ##########################
    # Connection
    ##########################

    async def _set_connected(self, is_connected: bool) -> None:
        """Set the connection state."""
        if is_connected:
            self.connection_event.set()
            self.msg_dict["is_on"] = True
        else:
            self.connection_event.clear()
            self.msg_dict["is_on"] = False
        await self._update_ha_state()

    def stop(self) -> None:
        """Stop reconnecting"""
        self.logger.info("Setting stop flags for tasks")
        self.stop_heartbeat.set()
        self.stop_commands_flag.set()

    async def _write_with_timeout(self, data: bytes) -> None:
        """Write data to the socket with a timeout."""
        if not self.connected:
            self.logger.error("Connection not established. Reconnecting")
            await self._reconnect()

        if not self.writer:
            self.logger.error("Writer is not initialized. Reconnecting")
            await self._reconnect()

        async def write_and_drain() -> None:
            if not self.writer:
                raise ConnectionError("Writer is not initialized")
            self.writer.write(data)
            await self.writer.drain()

        try:
            async with self.lock:
                await asyncio.wait_for(write_and_drain(), timeout=self.connect_timeout)
        except TimeoutError:
            self.logger.error(
                "Write operation timed out after %s seconds", self.connect_timeout
            )
            await self._reconnect()
        except (ConnectionResetError, OSError) as err:
            self.logger.error("Error writing to socket: %s", err)
            await self._reconnect()

    async def _reconnect(self) -> None:
        """
        Initiate a persistent connection to the device.

        Raises AckError, ConnectionError
        """
        # it will not try to connect until ping is successful
        if await self.is_device_connectable():
            self.logger.debug("Device is online")

            try:
                self.logger.debug("Connecting to Envy: %s:%s", self.host, self.port)

                # Command client
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),  # type: ignore[arg-type]
                    timeout=5,
                )
                self.logger.debug("Handshaking")
                self.logger.info("Waiting for envy to be available")

                await asyncio.sleep(SMALL_DELAY)
                # unblock heartbeat task
                await self._set_connected(True)
                self.stop_heartbeat.clear()
                # send a heartbeat now
                self.logger.debug("Sending heartbeat")
                await self.send_heartbeat(once=True)

                self.logger.info("Connection established")
                self.stop_commands_flag.clear()

            except (TimeoutError, HeartBeatError, OSError) as err:
                self.logger.error(
                    "Heartbeat failed. Connection not established %s", err
                )
                await self._set_connected(False)
                raise ConnectionError("Heartbeat failed") from err
        else:
            # the device is off
            self.logger.debug("Device is offline")
            await self._handle_power_off()

    async def is_device_connectable(self) -> bool:
        """Check if the device is connectable without ping. The device is only connectable when on."""
        retry_count = 0
        # loop because upgrading firmware can take a few seconds and will kill the connection
        while retry_count < 10:
            try:
                async with asyncio.timeout(SMALL_DELAY):
                    _, writer = await asyncio.open_connection(self.host, self.port)
                    writer.close()
                    await writer.wait_closed()
                    return True
            except (TimeoutError, ConnectionRefusedError, OSError):
                await asyncio.sleep(SMALL_DELAY)
                retry_count += 1
                continue
        self.logger.debug("Device is not connectable")
        return False

    async def _clear_attr(self) -> None:
        """
        Clear instance attr so HA doesn't report stale values and tells HA to write values to state
        """
        # Incoming attrs
        self.msg_dict = {"is_on": False}  # Clear attributes and set 'is_on' to False
        if self.update_callback:
            self.update_callback(self.msg_dict)

    async def close_connection(self) -> None:
        """Close the connection and clean up state."""
        self.logger.debug("Closing connection")

        if self.writer:
            try:
                # Try to send a graceful goodbye if possible
                if not self.writer.is_closing():
                    try:
                        async with self.lock:
                            self.writer.write(Connections.bye.value)
                            await self.writer.drain()
                    except (ConnectionError, OSError):
                        pass  # Ignore errors during goodbye

                self.writer.close()
                try:
                    await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
                except asyncio.TimeoutError:
                    self.logger.warning("Timeout waiting for writer to close")

            except Exception as e:
                self.logger.error("Error during connection close: %s", e)

        self.writer = None
        self.reader = None
        await self._set_connected(False)
        await self._clear_attr()
        self.logger.debug("Connection closed and state cleared")

    async def open_connection(self) -> None:
        """Open a connection with rate limiting."""
        self.logger.debug("Starting open connection")

        # Add rate limiting for connection attempts
        MAX_RETRIES = 3
        RETRY_DELAY = 15  # seconds

        for attempt in range(MAX_RETRIES):
            try:
                await self._reconnect()
                self.logger.debug("Connection opened successfully")

                # Refresh initial device state
                refresh_commands = [
                    ["GetIncomingSignalInfo"],
                    ["GetOutgoingSignalInfo"],
                    ["GetAspectRatio"],
                    ["GetMaskingRatio"],
                    ["GetMacAddress"],
                ]

                # Add commands with small delay between each to avoid overwhelming the device
                for cmd in refresh_commands:
                    await self.add_command_to_queue(cmd)
                    await asyncio.sleep(0.1)

                return

            except (AckError, ConnectionError) as err:
                self.logger.error(
                    "Error opening connection (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    err,
                )
                if attempt < MAX_RETRIES - 1:  # Don't sleep on last attempt
                    await asyncio.sleep(
                        min(RETRY_DELAY * 2**attempt, 300)
                    )  # Exponential backoff capped at 5min

        raise ConnectionError("Failed to open connection after multiple attempts")

    @property
    def connected(self) -> bool:
        """Check if the client is connected."""
        return self.connection_event.is_set()

    ##########################
    # Commands
    ##########################
    async def add_command_to_queue(self, command: Iterable[str]) -> None:
        """Add a command to the queue"""
        self.logger.info("Adding command to queue: %s", command)
        await self.command_queue.put(command)

    def clear_queue(self) -> None:
        """Clear queue."""
        self.logger.info("Clearing command queue")
        self.command_queue = asyncio.Queue()

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
        cmd: bytes = b""
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
                cmd = command_base + Footer.footer.value

            except KeyError as exc:
                raise NotImplementedError(
                    "Incorrect parameter given for command"
                ) from exc
        else:
            cmd = command_name + Footer.footer.value

        self.logger.debug("constructed command: %s", cmd)

        return cmd, val

    async def send_command(self, command: list) -> None:
        """
        Send a given command to the MadVR device.

        Args:
            command: A list containing the command to send.

        Raises:
            NotImplementedError: If the command is not supported.
            ConnectionError: If there's any connection-related issue.
        """
        try:
            cmd, enum_type = await self._construct_command(command)
        except NotImplementedError as err:
            self.logger.warning("Command not implemented: %s -- %s", command, err)
            raise

        self.logger.debug("Using values: %s %s", cmd, enum_type)

        try:
            await self._write_with_timeout(cmd)
        except (ConnectionResetError, TimeoutError, OSError) as err:
            self.logger.error("Error writing command to socket: %s", err)
            raise ConnectionError("Failed to send command") from err

    async def _process_notifications(self, msg: str) -> None:
        """process data in real time"""
        processed_data = await self.notification_processor.process_notifications(msg)

        if processed_data.get("power_off"):
            await self._handle_power_off()

        # only update HA if the data has changed
        if processed_data != self.msg_dict:
            self.msg_dict.update(processed_data)
            await self._update_ha_state()

    async def _handle_power_off(self) -> None:
        """Process out of band power off notifications"""
        self.powered_off_recently = True
        # this will mark the device as off
        await self._clear_attr()
        self.stop()
        await self.close_connection()

    async def _update_ha_state(self) -> None:
        if self.update_callback is not None:
            try:
                self.logger.info("Updating HA with %s", self.msg_dict)
                self.update_callback(self.msg_dict)
            except Exception as err:  # pylint: disable=broad-except
                self.logger.error("Error updating HA: %s", err)

    async def power_on(self, mac: str = "") -> None:
        """Power on the device with improved state handling."""

        # Reset flags before starting
        self.stop_commands_flag.clear()

        # use the detected mac or one that is supplied at init or function call
        mac_to_use = self.mac_address or self.mac or mac
        if mac_to_use:
            self.logger.debug("Turning on with mac %s", mac_to_use)
            send_magic_packet(mac_to_use, logger=self.logger)

            # Reset the powered_off flag after sending WOL
            # This allows the ping task to start checking connectivity
            self.powered_off_recently = False
        else:
            self.logger.warning(
                "No mac provided, no action to take. Implement your own WOL automation"
            )

    async def power_off(self, standby: bool = False) -> None:
        """Turn off madvr or set to standby with improved state handling."""
        self.stop()
        self.powered_off_recently = True

        if self.connected:
            try:
                await self.send_command(["Standby"] if standby else ["PowerOff"])
                # Give the device a moment to process the command
                await asyncio.sleep(SMALL_DELAY)
            except ConnectionError:
                self.logger.warning(
                    "Connection error while sending power off command - device might already be off"
                )

        await self.close_connection()
