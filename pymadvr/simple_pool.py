"""Simple connection pool for MadVR commands."""

import asyncio
import logging
import time
from typing import Optional

from pymadvr.commands import Connections
from pymadvr.consts import COMMAND_RESPONSE_TIMEOUT, CONNECTION_TIMEOUT


class MadvrConnection:
    """Individual MadVR connection wrapper."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, logger: logging.Logger):
        self.reader = reader
        self.writer = writer
        self.logger = logger
        self.created_at = time.time()
        self.last_used = time.time()

    async def is_healthy(self) -> bool:
        """Check if connection is still healthy."""
        if self.writer.is_closing():
            return False

        try:
            # Quick check - don't send heartbeat, just check if writer is open
            return not self.writer.is_closing()
        except Exception:
            return False

    async def send_command(self, command: bytes) -> Optional[str]:
        """Send a command and return the response."""
        try:
            self.writer.write(command)
            await self.writer.drain()

            # Read response with timeout
            deadline = asyncio.get_event_loop().time() + COMMAND_RESPONSE_TIMEOUT
            async with asyncio.timeout_at(deadline):
                response = await self.reader.read(1024)

            self.last_used = time.time()
            return response.decode("utf-8", errors="ignore").strip() if response else None

        except Exception as e:
            self.logger.debug(f"Command failed: {e}")
            raise ConnectionError(f"Failed to send command: {e}")

    async def close(self) -> None:
        """Close the connection."""
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()


class SimpleConnectionPool:
    """Simple connection pool that keeps one connection alive for 10 seconds after last use."""

    def __init__(self, host: str, port: int, logger: logging.Logger):
        self.host = host
        self.port = port
        self.logger = logger
        self.connection: Optional[MadvrConnection] = None
        self.close_timer: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()

    async def send_command(self, command: bytes) -> Optional[str]:
        """Send a command using the pooled connection."""
        async with self.lock:
            # Get or create connection
            conn = await self._get_connection()

            try:
                response = await conn.send_command(command)
                # Reset the close timer since we just used the connection
                self._reset_close_timer()
                return response
            except Exception as e:
                # Connection failed, close it and create a new one for retry
                await self._close_connection()
                self.logger.debug(f"Command failed, retrying with new connection: {e}")

                # Retry once with new connection
                conn = await self._get_connection()
                response = await conn.send_command(command)
                self._reset_close_timer()
                return response

    async def _get_connection(self) -> MadvrConnection:
        """Get a healthy connection or create a new one."""
        # Check if existing connection is healthy
        if self.connection and await self.connection.is_healthy():
            return self.connection

        # Create new connection
        await self._close_connection()  # Close any existing connection
        self.connection = await self._create_connection()
        return self.connection

    async def _create_connection(self) -> MadvrConnection:
        """Create a new connection."""
        try:
            # Create connection with timeout
            deadline = asyncio.get_event_loop().time() + CONNECTION_TIMEOUT
            async with asyncio.timeout_at(deadline):
                reader, writer = await asyncio.open_connection(self.host, self.port)

            # Wait for welcome message
            deadline = asyncio.get_event_loop().time() + COMMAND_RESPONSE_TIMEOUT
            async with asyncio.timeout_at(deadline):
                welcome = await reader.read(1024)

            if Connections.welcome.value not in welcome:
                raise ConnectionError("Did not receive welcome message")

            return MadvrConnection(reader, writer, self.logger)

        except Exception as e:
            self.logger.error(f"Failed to create pooled connection: {e}")
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")

    def _reset_close_timer(self) -> None:
        """Reset the timer to close the connection after 10 seconds of inactivity."""
        # Cancel existing timer
        if self.close_timer and not self.close_timer.done():
            self.close_timer.cancel()

        # Start new timer
        self.close_timer = asyncio.create_task(self._close_after_delay())

    async def _close_after_delay(self) -> None:
        """Close the connection after 10 seconds of inactivity."""
        try:
            await asyncio.sleep(10.0)  # 10 second delay
            async with self.lock:
                if self.connection:
                    await self._close_connection()
        except asyncio.CancelledError:
            # Timer was cancelled, connection is still being used
            pass

    async def _close_connection(self) -> None:
        """Close the current connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None

    async def close_all(self) -> None:
        """Close all connections and cancel timers."""
        if self.close_timer and not self.close_timer.done():
            self.close_timer.cancel()
        await self._close_connection()
