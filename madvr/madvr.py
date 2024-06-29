"""
Implements the MadVR protocol
"""

import asyncio
import logging
import os  # For ping functionality
from typing import Any, Final, Iterable

from madvr.commands import Commands, Connections, Footer
from madvr.errors import AckError, HeartBeatError, RetryExceededError
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
        port: int = 44077,
        # if blank, power off will use standby mode and poweron will require device to be in standby
        mac: str = "",
        connect_timeout: int = 5,
        heartbeat_interval: int = 15,
        ping_interval: int = 5,
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

        self.read_limit: int = 8000
        self.command_read_timeout: int = 3

        # self.async_write_ha_state from HA
        self.update_callback: Any = None

        self.notification_processor = NotificationProcessor(self.logger)
        self.powered_off_recently: bool = False
        self.ping_delay_after_power_off: int = 30
        self.logger.debug("Running in debug mode")

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return self.msg_dict.get("is_on", False)

    def set_update_callback(self, callback: Any) -> None:
        """Function to set the callback for updating HA state"""
        self.update_callback = callback

    async def async_add_tasks(self) -> None:
        """Add background tasks."""
        # loop can be passed from HA
        if not self.loop:
            self.loop = asyncio.get_event_loop()

        task_queue = self.loop.create_task(self.handle_queue())
        self.tasks.append(task_queue)

        task_notif = self.loop.create_task(self.read_notifications())
        self.tasks.append(task_notif)

        task_hb = self.loop.create_task(self.send_heartbeat())
        self.tasks.append(task_hb)

        # this will only be cancelled on unload so thats fine
        if self.mac:
            # only start the ping task if a mac is provided because it doesnt matter if its on standby
            task_ping = self.loop.create_task(self.ping_until_alive())
            self.tasks.append(task_ping)

    async def async_cancel_tasks(self) -> None:
        """Cancel all tasks."""
        for task in self.tasks:
            if not task.done():
                task.cancel()

    async def _clear_attr(self) -> None:
        """
        Clear instance attr so HA doesn't report stale values and tells HA to write values to state
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
        await self._clear_attr()

    async def open_connection(self) -> None:
        """Open a connection"""
        self.logger.debug("Starting open connection")
        try:
            await self._reconnect()
            self.logger.debug("Connection opened")
        except AckError as err:
            self.logger.error(err)

        # once connected, try to refresh data once in the case the device was turned connected to while on already
        cmds = [
            ["GetIncomingSignalInfo"],
            ["GetOutgoingSignalInfo"],
            ["GetAspectRatio"],
            ["GetMaskingRatio"],
        ]
        for cmd in cmds:
            await self.add_command_to_queue(cmd)

    def connected(self) -> bool:
        """Check if the client is connected."""
        return (
            self.reader is not None
            and self.writer is not None
            and not self.reader.at_eof()
        )

    async def handle_queue(self) -> None:
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
                except ConnectionResetError:
                    self.logger.warning("Envy was turned off manually")
                    # update state that its off
                    await self._clear_attr()
                except AttributeError:
                    self.logger.warning("Issue sending command from queue")
                except RetryExceededError:
                    self.logger.warning("Retry exceeded for command %s", command)
                except OSError as err:
                    self.logger.error("Unexpected error when sending command: %s", err)
                finally:
                    self.command_queue.task_done()

            if self.stop_commands_flag.is_set():
                self.clear_queue()
                self.logger.debug("Stopped processing commands")
                break

            await asyncio.sleep(0.1)

    async def add_command_to_queue(self, command: Iterable[str]) -> None:
        """Add a command to the queue"""
        await self.command_queue.put(command)

    def clear_queue(self) -> None:
        """Clear queue."""
        self.command_queue = asyncio.Queue()

    def stop(self) -> None:
        """Stop reconnecting"""
        self.stop_heartbeat.set()
        self.stop_commands_flag.set()

    async def ping_until_alive(self) -> None:
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

    # TODO: this should return a bool
    async def _reconnect(self) -> None:
        """
        Initiate keep-alive connection. This should handle any error and reconnect eventually.

        Raises AckError
        """
        # it will not try to connect until ping is successful
        if await self.ping_device():
            self.logger.debug("Device is online")

            try:
                self.logger.info("Connecting to Envy: %s:%s", self.host, self.port)

                # Command client
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),  # type: ignore[arg-type]
                    timeout=5,
                )
                self.logger.debug("Handshaking")
                self.logger.info("Waiting for envy to be available")

                await asyncio.sleep(3)
                # unblock heartbeat task
                self.stop_heartbeat.clear()
                # TODO: verify heartbeat by reading for heartbeat ok
                await self.send_heartbeat(once=True)

                self.logger.info("Connection established")
                self.connection_event.set()

                # device cannot be off if we are connected
                self.msg_dict["is_on"] = True
                await self._update_ha_state()

            except HeartBeatError:
                self.logger.warning(
                    "Error sending heartbeat, retrying in %s seconds", 2
                )
                # TODO: this should fail not retry, this doesnt retry anymore anyway
                await asyncio.sleep(2)
            except TimeoutError:
                self.logger.error("Connecting timed out")
            except OSError as err:
                self.logger.error("Connecting failed %s", err)
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

    async def send_heartbeat(self, once: bool = False) -> None:
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
                    if self.writer:
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
                    if self.writer:
                        self.writer.write(self.HEARTBEAT)
                        await self.writer.drain()
                self.logger.debug("heartbeat complete")
            except asyncio.TimeoutError as err:
                self.logger.error("timeout when sending heartbeat %s", err)
            except OSError as err:
                self.logger.error("error when sending heartbeat %s", err)
                await self._clear_attr()
                # this means something went wrong with the connection
                await self.close_connection()
                await self._reconnect()
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
                    if self.writer:
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
                if self.reader:
                    msg = await asyncio.wait_for(
                        self.reader.read(self.read_limit),
                        timeout=self.command_read_timeout,
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
        await self._clear_attr()
        self.stop()
        await self.close_connection()

    async def _update_ha_state(self) -> None:
        if self.update_callback is not None:
            try:
                self.update_callback(self.msg_dict)
            except Exception as err:  # pylint: disable=broad-except
                self.logger.error("Error updating HA: %s", err)

    async def power_on(self) -> None:
        """
        Power on the device
        """
        # start processing commands
        self.stop_commands_flag.clear()

        if self.mac:
            # this will allow ping to trigger the connection
            self.logger.debug("Sending magic packet to %s", self.mac)
            send_magic_packet(self.mac, logger=self.logger)
        else:
            self.logger.debug("No mac provided, assuming device is on standby")
            # if no mac was provided, assume its on standby and connect
            await self._reconnect()
            # any remote command will trigger power on
            await self.add_command_to_queue(["CloseMenu"])

    async def power_off(self, standby: bool = False) -> None:
        """
        turn off madvr or set to standby

        standby: bool -> standby instead of poweroff if true
        """
        self.stop()
        # set the flag to delay the ping task to avoid race conditions
        self.powered_off_recently = True
        if self.connected():
            if self.mac:
                await self.send_command(["Standby"] if standby else ["PowerOff"])
            else:
                await self.send_command(["Standby"])

        await self.close_connection()
