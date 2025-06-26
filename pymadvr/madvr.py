"""
Implements the MadVR protocol with connection-per-command architecture
"""

import asyncio
import logging
import time
from typing import Any, Final, Iterable

from pymadvr.commands import Commands, Connections, Footer
from pymadvr.consts import (
    COMMAND_RESPONSE_TIMEOUT,
    COMMAND_TIMEOUT,
    CONNECT_TIMEOUT,
    CONNECTION_TIMEOUT,
    DEFAULT_PORT,
    MAX_COMMAND_QUEUE_SIZE,
    PING_INTERVAL,
    REFRESH_TIME,
    TASK_CPU_DELAY,
)
from pymadvr.notifications import NotificationProcessor
from pymadvr.simple_pool import SimpleConnectionPool
from pymadvr.wol import send_magic_packet


class Madvr:
    """MadVR Control with connection-per-command architecture"""

    def __init__(
        self,
        host: str,
        logger: logging.Logger = logging.getLogger(__name__),
        port: int = DEFAULT_PORT,
        mac: str = "",
        connect_timeout: int = CONNECT_TIMEOUT,
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        self.host = host
        self.port = port
        self.mac = mac
        self.connect_timeout: int = connect_timeout
        self.logger = logger

        # Simple connection pool for user commands
        self.connection_pool = SimpleConnectionPool(host, port, logger)

        # Background tasks
        self.notification_task: asyncio.Task[None] | None = None
        self.notification_heartbeat_task: asyncio.Task[None] | None = None
        self.ping_task: asyncio.Task[None] | None = None
        self.refresh_task: asyncio.Task[None] | None = None
        self.queue_task: asyncio.Task[None] | None = None
        self.notification_reader: asyncio.StreamReader | None = None
        self.notification_writer: asyncio.StreamWriter | None = None

        # User command queue for FIFO processing
        self.user_command_queue: asyncio.Queue[list[str]] = asyncio.Queue(maxsize=MAX_COMMAND_QUEUE_SIZE)
        self.stop_queue = asyncio.Event()

        # Event to track if notification connection is ready
        self.notification_connected = asyncio.Event()
        self.stop_notifications = asyncio.Event()

        self.loop = loop
        self.command_read_timeout: int = COMMAND_TIMEOUT

        # Const values
        self.MADVR_OK: Final = Connections.welcome.value
        self.HEARTBEAT: Final = Connections.heartbeat.value

        # Stores all attributes from notifications
        self.msg_dict: dict[str, Any] = {}

        # Callback for HA state updates
        self.update_callback: Any = None

        self.notification_processor = NotificationProcessor(self.logger)
        self.powered_off_recently: bool = False

    ##########################
    # Properties
    ##########################
    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return self.msg_dict.get("is_on", False)

    @property
    def mac_address(self) -> str:
        """Return the mac address of the device."""
        return self.msg_dict.get("mac_address", "")

    @property
    def connected(self) -> bool:
        """Return true if notification connection is established."""
        return self.notification_connected.is_set()

    def set_update_callback(self, callback: Any) -> None:
        """Function to set the callback for updating HA state"""
        self.update_callback = callback

    ##########################
    # Task Management
    ##########################
    async def async_add_tasks(self) -> None:
        """Start background tasks."""
        if not self.loop:
            self.loop = asyncio.get_event_loop()

        # Start notification task
        self.notification_task = self.loop.create_task(self._notification_task_wrapper())
        self.notification_task.set_name("notifications")

        # Start notification heartbeat task
        self.notification_heartbeat_task = self.loop.create_task(self._notification_heartbeat_wrapper())
        self.notification_heartbeat_task.set_name("notification_heartbeat")

        # Start ping task for device monitoring
        self.ping_task = self.loop.create_task(self._ping_task_wrapper())
        self.ping_task.set_name("ping")

        # Start refresh task for periodic data updates
        self.refresh_task = self.loop.create_task(self._refresh_task_wrapper())
        self.refresh_task.set_name("refresh")

        # Start queue processing task for user commands
        self.queue_task = self.loop.create_task(self._queue_task_wrapper())
        self.queue_task.set_name("queue")

        self.logger.debug("Started background tasks")

    async def _notification_task_wrapper(self) -> None:
        """Wrapper for notification task with error handling."""
        try:
            await self.task_read_notifications()
        except asyncio.CancelledError:
            self.logger.debug("Notification task was cancelled")
        except Exception as e:
            self.logger.exception("Notification task failed: %s", e)

    async def _ping_task_wrapper(self) -> None:
        """Wrapper for ping task with error handling."""
        try:
            await self.task_ping_device()
        except asyncio.CancelledError:
            self.logger.debug("Ping task was cancelled")
        except Exception as e:
            self.logger.exception("Ping task failed: %s", e)

    async def _refresh_task_wrapper(self) -> None:
        """Wrapper for refresh task with error handling."""
        try:
            await self.task_refresh_info()
        except asyncio.CancelledError:
            self.logger.debug("Refresh task was cancelled")
        except Exception as e:
            self.logger.exception("Refresh task failed: %s", e)

    async def _queue_task_wrapper(self) -> None:
        """Wrapper for queue task with error handling."""
        try:
            await self.task_process_command_queue()
        except asyncio.CancelledError:
            self.logger.debug("Queue task was cancelled")
        except Exception as e:
            self.logger.exception("Queue task failed: %s", e)

    async def _notification_heartbeat_wrapper(self) -> None:
        """Wrapper for notification heartbeat task with error handling."""
        try:
            await self.task_notification_heartbeat()
        except asyncio.CancelledError:
            self.logger.debug("Notification heartbeat task was cancelled")
        except Exception as e:
            self.logger.exception("Notification heartbeat task failed: %s", e)

    async def async_cancel_tasks(self) -> None:
        """Cancel background tasks (except ping which monitors device state)."""
        self.stop_notifications.set()
        self.stop_queue.set()

        # Cancel notification task
        if self.notification_task and not self.notification_task.done():
            self.notification_task.cancel()
            try:
                await self.notification_task
            except asyncio.CancelledError:
                pass

        # Cancel notification heartbeat task
        if self.notification_heartbeat_task and not self.notification_heartbeat_task.done():
            self.notification_heartbeat_task.cancel()
            try:
                await self.notification_heartbeat_task
            except asyncio.CancelledError:
                pass

        # Cancel queue task
        if self.queue_task and not self.queue_task.done():
            self.queue_task.cancel()
            try:
                await self.queue_task
            except asyncio.CancelledError:
                pass

        # Close notification connection
        if self.notification_writer:
            try:
                self.notification_writer.close()
                await self.notification_writer.wait_closed()
            except Exception:
                pass

        self.notification_reader = None
        self.notification_writer = None
        self.notification_connected.clear()

        # Close the simple connection pool
        await self.connection_pool.close_all()

        self.logger.debug("Cancelled notification task and closed connections")

    ##########################
    # Connection Management
    ##########################
    async def open_connection(self) -> None:
        """Start background tasks. The heartbeat task will handle establishing the notification connection."""
        try:
            # Start all background tasks
            self.logger.debug("Starting background tasks")
            await self.async_add_tasks()

            # Wait for heartbeat task to establish connection
            await asyncio.sleep(0.5)

            # Get initial device information
            self.logger.debug("Fetching initial device information")
            await self._get_initial_device_info()

            self.logger.info("MadVR client initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize MadVR client: {e}")
            raise ConnectionError(f"Failed to initialize client for {self.host}:{self.port}") from e

    async def _establish_notification_connection(self) -> None:
        """Establish dedicated connection for notifications."""
        try:
            self.notification_reader, self.notification_writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.connect_timeout
            )

            if not self.notification_reader:
                raise ConnectionError("Reader not available")
            welcome = await asyncio.wait_for(self.notification_reader.read(1024), timeout=5.0)

            if self.MADVR_OK not in welcome:
                raise ConnectionError("Did not receive welcome message")

            self.notification_connected.set()
            self.logger.debug("Notification connection established")

        except Exception as e:
            # Clean up on failure
            if self.notification_writer:
                self.notification_writer.close()
                await self.notification_writer.wait_closed()
            self.notification_reader = None
            self.notification_writer = None
            raise ConnectionError(f"Failed to establish notification connection: {e}")

    async def _get_initial_device_info(self) -> None:
        """Get initial device information using command connections."""
        initial_commands = [
            ["GetMacAddress"],
            ["GetTemperatures"],
            # Get signal info in case a change was missed
            ["GetIncomingSignalInfo"],
            ["GetOutgoingSignalInfo"],
            ["GetAspectRatio"],
            ["GetMaskingRatio"],
        ]

        for command in initial_commands:
            try:
                await self.send_command(command)
            except Exception as e:
                self.logger.debug(f"Failed to get initial info with {command}: {e}")

    async def close_connection(self) -> None:
        """Close all connections."""
        await self.async_cancel_tasks()

    def stop(self) -> None:
        """Stop operations."""
        self.stop_notifications.set()

    ##########################
    # Command Execution
    ##########################
    async def send_command(self, command: list[str], direct: bool = False) -> str | None:
        """
        Send a command using connection pool or direct connection.

        Args:
            command: A list containing the command to send.
            direct: If True, use direct connection. If False, use connection pool.

        Returns:
            Response from the device or None

        Raises:
            NotImplementedError: If the command is not supported.
            ConnectionError: If there's any connection-related issue.
        """
        try:
            cmd, _ = await self._construct_command(command)
        except NotImplementedError as err:
            self.logger.warning("Command not implemented: %s -- %s", command, err)
            raise

        self.logger.debug("Sending command: %s", cmd)

        try:
            if direct:
                # Use bespoke connection
                response = await self._send_command_direct(cmd)
            else:
                # Use connection pool
                response = await self.connection_pool.send_command(cmd)
            return response
        except Exception as e:
            self.logger.error(f"Failed to send command {command}: {e}")
            raise

    async def _send_command_direct(self, cmd: bytes) -> str | None:
        """Send a command using a direct connection - no pooling."""
        writer = None
        try:
            deadline = asyncio.get_event_loop().time() + CONNECTION_TIMEOUT
            async with asyncio.timeout_at(deadline):
                reader, writer = await asyncio.open_connection(self.host, self.port)

            deadline = asyncio.get_event_loop().time() + COMMAND_RESPONSE_TIMEOUT
            async with asyncio.timeout_at(deadline):
                welcome = await reader.read(1024)

            if b"WELCOME" not in welcome:
                raise ConnectionError("Did not receive welcome message")

            writer.write(cmd)
            await writer.drain()

            deadline = asyncio.get_event_loop().time() + COMMAND_RESPONSE_TIMEOUT
            async with asyncio.timeout_at(deadline):
                response = await reader.read(1024)

            return response.decode("utf-8", errors="ignore").strip() if response else None

        except asyncio.TimeoutError:
            raise ConnectionError("Timeout sending command")
        except Exception as e:
            raise ConnectionError(f"Failed to send command: {e}")
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

    async def _send_command_via_notification(self, command: list[str]) -> bool:
        """
        Send a command via the notification connection.

        The response will come back as a notification and be processed by the notification task.
        This is used by background tasks that want their responses processed as notifications.

        Returns True if command was sent successfully.
        """
        if not self.notification_writer or not self.notification_connected.is_set():
            self.logger.debug("Cannot send command via notification - connection not available")
            return False

        try:
            cmd, _ = await self._construct_command(command)
            self.notification_writer.write(cmd)
            await self.notification_writer.drain()
            self.logger.debug(f"Sent command via notification connection: {command}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send command via notification connection: {e}")
            return False

    async def add_command_to_queue(self, command: Iterable[str]) -> None:
        """
        Add user command to queue for FIFO processing.

        User commands (menu navigation, key presses) are queued to preserve ordering.
        System commands should use send_command() directly for immediate execution.
        """
        command_list = list(command)
        try:
            self.user_command_queue.put_nowait(command_list)
            self.logger.debug(f"Added command to queue: {command_list}")
        except asyncio.QueueFull:
            self.logger.error(f"Command queue is full, dropping command: {command_list}")
        except Exception as e:
            self.logger.error(f"Failed to queue command {command_list}: {e}")

    def clear_queue(self) -> None:
        """Clear all pending commands from the user command queue."""
        try:
            while not self.user_command_queue.empty():
                self.user_command_queue.get_nowait()
                self.user_command_queue.task_done()
            self.logger.debug("Cleared command queue")
        except Exception as e:
            self.logger.error(f"Error clearing queue: {e}")

    ##########################
    # Notification Handling
    ##########################
    async def task_read_notifications(self) -> None:
        """
        Read notifications from the dedicated notification connection.
        """
        while not self.stop_notifications.is_set():
            # Wait for notification connection to be established
            if not self.notification_connected.is_set():
                self.logger.debug("Waiting for notification connection to be established...")
                await asyncio.sleep(1.0)
                continue
            try:
                if not self.notification_reader:
                    # Connection lost - heartbeat task will handle reconnection
                    await asyncio.sleep(TASK_CPU_DELAY)
                    continue

                msg = await asyncio.wait_for(
                    self.notification_reader.read(1024),
                    timeout=COMMAND_RESPONSE_TIMEOUT,
                )

                if not msg:
                    self.logger.debug("Empty notification message")
                    continue

                try:
                    await self._process_notifications(msg.decode("utf-8"))
                except UnicodeDecodeError as e:
                    self.logger.error("Failed to decode notification: %s", e)
                    continue

            except asyncio.TimeoutError:
                # No notifications to read
                await asyncio.sleep(TASK_CPU_DELAY)
                continue

            except (ConnectionResetError, BrokenPipeError) as err:
                self.logger.error(f"Notification connection error: {err}")
                # Clear connection state - heartbeat task will handle reconnection
                self.notification_reader = None
                self.notification_writer = None
                self.notification_connected.clear()
                await asyncio.sleep(TASK_CPU_DELAY)
                continue

            except Exception as e:
                self.logger.exception("Unexpected error in notification task: %s", e)
                await asyncio.sleep(TASK_CPU_DELAY)
                continue

            await asyncio.sleep(TASK_CPU_DELAY)

    async def _process_notifications(self, msg: str) -> None:
        """Process notification data in real time."""
        processed_data = await self.notification_processor.process_notifications(msg)

        self.msg_dict["_last_update"] = time.time()

        if processed_data.get("power_off"):
            await self._handle_power_off()

        # Only update HA if the data has changed
        if processed_data != self.msg_dict:
            self.msg_dict.update(processed_data)
            await self._update_ha_state()

    async def _handle_power_off(self) -> None:
        """Process power off notifications."""
        self.powered_off_recently = True
        await self._clear_attr()
        self.stop()

    async def _update_ha_state(self) -> None:
        """Update Home Assistant state."""
        if self.update_callback is not None:
            try:
                self.logger.debug("Updating HA with %s", self.msg_dict)
                self.update_callback(self.msg_dict)
            except Exception as e:
                self.logger.error(f"Failed to update HA state: {e}")

    async def _clear_attr(self) -> None:
        """Clear device attributes."""
        for key in list(self.msg_dict.keys()):
            if key not in ["mac_address"]:  # Keep MAC address
                del self.msg_dict[key]

        self.msg_dict["is_on"] = False
        await self._update_ha_state()

    ##########################
    # Device Control Methods
    ##########################
    async def power_on(self, mac: str = "") -> None:
        """Turn on the device using Wake on LAN."""
        if self.stop_notifications.is_set():
            self.logger.warning("Cannot power on - client is stopped")
            return

        mac = self.mac_address or self.mac or mac
        if not mac:
            self.logger.error("No MAC address available for Wake on LAN")
            return

        try:
            send_magic_packet(mac, logger=self.logger)
            self.logger.debug("Sent Wake on LAN packet")
        except Exception as e:
            self.logger.error(f"Failed to send WOL packet: {e}")

    async def power_off(self, standby: bool = False) -> None:
        """Turn off the device."""
        command = ["Standby"] if standby else ["PowerOff"]

        try:
            await self.send_command(command)
            self.stop()
            await self.close_connection()
            self.powered_off_recently = True
        except Exception as e:
            self.logger.error(f"Failed to power off device: {e}")

    async def display_message(self, duration: int, message: str) -> None:
        """Display a message on the device."""
        await self.add_command_to_queue(["DisplayMessage", str(duration), f'"{message}"'])

    async def display_audio_volume(self, channel: int, current: int, max_vol: int, unit: str) -> None:
        """Display audio volume information."""
        await self.add_command_to_queue(["DisplayAudioVolume", str(channel), str(current), str(max_vol), f'"{unit}"'])

    async def display_audio_mute(self) -> None:
        """Display audio mute indicator."""
        await self.add_command_to_queue(["DisplayAudioMute"])

    async def close_audio_mute(self) -> None:
        """Close audio mute indicator."""
        await self.add_command_to_queue(["CloseAudioMute"])

    ##########################
    # Helper Methods
    ##########################
    async def _construct_command(self, command: list[str]) -> tuple[bytes, str]:
        """Construct the command bytes from command list."""
        if not command:
            raise NotImplementedError("Empty command")

        command_name = command[0]

        # Find the command in the Commands enum
        for cmd_enum in Commands:
            # All command enum values are tuples with bytes as first element
            if hasattr(cmd_enum.value, "__len__") and len(cmd_enum.value) >= 1:
                cmd_bytes = cmd_enum.value[0]
                # Check if this is the command we're looking for
                if cmd_bytes.decode("utf-8", errors="ignore").rstrip() == command_name:
                    # Build full command
                    full_command = cmd_bytes

                    # Add parameters if any
                    if len(command) > 1:
                        params = " ".join(command[1:])
                        full_command += b" " + params.encode("utf-8")

                    # Add footer
                    full_command += Footer.footer.value

                    return full_command, str(type(cmd_enum.value[1]))

        raise NotImplementedError(f"Command '{command_name}' not found")

    # Legacy compatibility methods (simplified)
    async def is_device_connectable(self) -> bool:
        """Check if device is connectable by trying a quick connection."""
        try:
            deadline = asyncio.get_event_loop().time() + 1.0  # 1 second timeout
            async with asyncio.timeout_at(deadline):
                _, writer = await asyncio.open_connection(self.host, self.port)
                writer.close()
                await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _set_connected(self, connected: bool) -> None:
        """Set connection state (compatibility method)."""
        if connected:
            self.notification_connected.set()
        else:
            self.notification_connected.clear()

    async def task_refresh_info(self) -> None:
        """
        Refresh device information forever when device is on.

        This task runs forever and updates display information when the device is powered on.
        It automatically pauses when the device is off to save resources.
        """
        # Add initial delay to prevent race condition with startup commands
        await asyncio.sleep(5)

        while True:
            try:
                if self.connected and self.msg_dict.get("is_on", False):
                    # Get current display information
                    refresh_commands = [
                        ["GetMacAddress"],
                        ["GetTemperatures"],
                        # Get signal info in case a change was missed
                        ["GetIncomingSignalInfo"],
                        ["GetOutgoingSignalInfo"],
                        ["GetAspectRatio"],
                        ["GetMaskingRatio"],
                    ]

                    for command in refresh_commands:
                        try:
                            # Send via notification connection so responses are processed as notifications
                            success = await self._send_command_via_notification(command)
                            if not success:
                                self.logger.debug(
                                    f"Failed to send refresh command {command[0]} via notification connection"
                                )
                        except Exception as e:
                            self.logger.debug(f"Failed to refresh {command[0]}: {e}")

                    await asyncio.sleep(REFRESH_TIME)
                else:
                    # Device is off or not connected, wait before checking again
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.debug(f"Info refresh failed: {e}")
                await asyncio.sleep(REFRESH_TIME)

    async def task_ping_device(self) -> None:
        """
        This task should not be cancelled during normal operation as it:
        - Determines if the device is on/off
        - Pre-warms the connection pool for faster command execution
        - Updates device power state based on connectivity

        Only stop this task during complete instance destruction.
        """
        while True:
            try:
                # Try to establish a connection (this is our "ping")
                is_available = await self.is_device_connectable()

                if is_available:
                    # Device is on - update state
                    if not self.msg_dict.get("is_on", False):
                        self.logger.debug("Device detected as online")
                        self.msg_dict["is_on"] = True
                        await self._update_ha_state()

                else:
                    # Device is off - update state
                    if self.msg_dict.get("is_on", False):
                        self.logger.debug("Device detected as offline")
                        self.msg_dict["is_on"] = False
                        await self._update_ha_state()

                # Wait before next ping
                await asyncio.sleep(PING_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error in ping task: {e}")
                await asyncio.sleep(PING_INTERVAL)

    async def task_process_command_queue(self) -> None:
        """
        Process user commands from queue in FIFO order.

        This task ensures user interactions (menu navigation, key presses) are
        executed in the correct order, which is critical for proper operation.
        """
        while not self.stop_queue.is_set():
            try:
                # Wait for a command with timeout to allow checking stop event
                command = await asyncio.wait_for(self.user_command_queue.get(), timeout=1.0)

                try:
                    # Execute the command immediately (no additional queuing)
                    await self.send_command(command)
                    self.logger.debug(f"Processed queued command: {command}")
                except Exception as e:
                    self.logger.error(f"Failed to execute queued command {command}: {e}")
                finally:
                    # Mark task as done regardless of success/failure
                    self.user_command_queue.task_done()

                # Prevent CPU spinning
                await asyncio.sleep(0.1)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error in queue processing task: {e}")
                await asyncio.sleep(TASK_CPU_DELAY)

    async def task_notification_heartbeat(self) -> None:
        """
        Send heartbeat to notification connection to keep it alive.

        MadVR closes connections after 60 seconds without activity.
        Send heartbeat every 30 seconds to ensure connection stays alive.
        """
        last_heartbeat = 0.0

        while not self.stop_notifications.is_set():
            try:
                # Check if we need to establish/re-establish connection
                if (
                    not self.notification_connected.is_set()
                    or not self.notification_writer
                    or self.notification_writer.is_closing()
                ):
                    self.logger.info("Heartbeat task establishing notification connection...")
                    try:
                        await self._establish_notification_connection()
                        self.logger.info("Notification connection established by heartbeat task")
                        last_heartbeat = time.time()
                    except Exception as e:
                        self.logger.error(f"Failed to establish notification connection: {e}")
                        await asyncio.sleep(5.0)  # Wait before retry
                        continue

                # Check if it's time to send heartbeat (every 30 seconds)
                current_time = time.time()
                if current_time - last_heartbeat >= 30.0:
                    # Send heartbeat command
                    if self.notification_writer:
                        self.notification_writer.write(self.HEARTBEAT)
                        await self.notification_writer.drain()
                        self.logger.debug("Sent heartbeat to notification connection")
                        last_heartbeat = current_time

                # Avoid busy loop
                await asyncio.sleep(1.0)

            except Exception as e:
                self.logger.error(f"Error sending heartbeat: {e}")
                # Clear state for reconnection
                self.notification_reader = None
                self.notification_writer = None
                self.notification_connected.clear()
                await asyncio.sleep(5.0)  # Wait a bit before retry
