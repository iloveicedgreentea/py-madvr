"""Connection pool for MadVR connections."""

import asyncio
import logging
import time
from typing import List, Optional

from pymadvr.commands import Connections
from pymadvr.consts import (
    COMMAND_RESPONSE_TIMEOUT,
    COMMAND_RETRY_ATTEMPTS,
    CONNECTION_POOL_MAX_SIZE,
    CONNECTION_TIMEOUT,
    HEARTBEAT_TIMEOUT,
)


class MadvrConnection:
    """Individual MadVR connection wrapper."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, logger: logging.Logger):
        self.reader = reader
        self.writer = writer
        self.logger = logger
        self.created_at = time.time()
        self.last_used = time.time()
        self._closed = False

    async def _send_heartbeat(self, timeout: float = HEARTBEAT_TIMEOUT) -> bool:
        """Send a heartbeat command to keep connection alive."""
        try:
            self.writer.write(Connections.heartbeat.value)
            await asyncio.wait_for(self.writer.drain(), timeout=timeout)
            self.last_used = time.time()
            return True
        except Exception as e:
            self.logger.debug(f"Heartbeat failed: {e}")
            return False

    async def is_healthy(self) -> bool:
        """Check if connection is still healthy by sending a heartbeat."""
        if self._closed:
            return False
        if self.writer.is_closing():
            return False
        # Try to send a heartbeat with short timeout to verify connection
        try:
            if await asyncio.wait_for(self._send_heartbeat(), timeout=0.1):
                self.logger.debug("Connection health check passed")
                return True
            else:
                self.logger.debug("Connection health check failed")
                return False
        except asyncio.TimeoutError:
            self.logger.warning("Connection health check timed out")
            return False

    async def send_command(self, command: bytes) -> Optional[str]:
        """Send a command and return the response."""

        try:
            self.writer.write(command)
            await self.writer.drain()

            # Read response
            response = await asyncio.wait_for(self.reader.read(1024), timeout=COMMAND_RESPONSE_TIMEOUT)

            self.last_used = time.time()
            return response.decode("utf-8", errors="ignore")

        except Exception as e:
            self.logger.debug(f"Command failed: {e}")
            await self.close()
            raise ConnectionError(f"Failed to send command: {e}")

    async def close(self) -> None:
        """Close the connection."""
        if self._closed:
            return

        self._closed = True
        try:
            if not self.writer.is_closing():
                self.writer.close()
                await self.writer.wait_closed()
        except Exception as e:
            self.logger.debug(f"Error closing connection: {e}")


class ConnectionPool:
    """Pool of MadVR connections for reuse."""

    def __init__(self, host: str, port: int, logger: logging.Logger):
        self.host = host
        self.port = port
        self.logger = logger
        self.pool: List[MadvrConnection] = []

    async def send_command(self, command: bytes) -> Optional[str]:
        """Send a command using a pooled connection, with automatic retry."""
        # Try to send command, retry if it fails
        for attempt in range(COMMAND_RETRY_ATTEMPTS):
            self.logger.debug(f"Sending command: {command.decode('utf-8', errors='ignore')}")
            conn = await self.get_connection()
            try:
                response = await conn.send_command(command)
                # Success - return connection to pool
                await self.return_connection(conn)
                return response
            except ConnectionError as e:
                # Connection failed - it's already closed by send_command
                if attempt == 0:
                    self.logger.warning(f"Command failed on first attempt, retrying with new connection: {e}")
                    continue
                else:
                    self.logger.error(f"Command failed after retry: {e}")
                    raise ConnectionError(f"Failed to send command after retry: {e}")
            except Exception as e:
                # Unexpected error - return connection to pool
                await self.return_connection(conn)
                self.logger.error(f"Unexpected error sending command: {e}")
                raise
        # This shouldn't be reached, but mypy requires explicit return
        return None

    async def get_connection(self) -> MadvrConnection:
        """Get a connection - create new one each time for simplicity."""
        return await self._create_connection()

    async def return_connection(self, conn: MadvrConnection) -> None:
        """Close the connection - no pooling for simplicity."""
        await conn.close()
        self.logger.debug("Closed connection after use")

    async def _create_connection(self) -> MadvrConnection:
        """Create a new MadVR connection."""

        writer = None
        try:
            self.logger.debug(f"Creating new connection to {self.host}:{self.port}")

            # Use timeout_at instead of wait_for
            deadline = asyncio.get_event_loop().time() + CONNECTION_TIMEOUT
            async with asyncio.timeout_at(deadline):
                reader, writer = await asyncio.open_connection(self.host, self.port)

            self.logger.debug("waiting for welcome message...")
            # Wait for welcome message with timeout_at
            deadline = asyncio.get_event_loop().time() + COMMAND_RESPONSE_TIMEOUT
            async with asyncio.timeout_at(deadline):
                welcome = await reader.read(1024)

            if Connections.welcome.value not in welcome:
                raise ConnectionError("Did not receive welcome message")

            self.logger.debug("Successfully created new connection")
            return MadvrConnection(reader, writer, self.logger)

        except asyncio.TimeoutError as e:
            if writer:
                writer.close()
                await writer.wait_closed()
            self.logger.error(f"Connection timeout to {self.host}:{self.port}: {e}")
            raise ConnectionError(f"Connection timeout to {self.host}:{self.port}")
        except Exception as e:
            if writer:
                writer.close()
                await writer.wait_closed()
            self.logger.error(f"Failed to create connection: {type(e).__name__}: {e}")
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {type(e).__name__}: {e}")

    async def close_all(self) -> None:
        """Close all connections in the pool."""
        for conn in self.pool:
            await conn.close()
        self.pool.clear()
        self.logger.debug("Closed all pooled connections")

    async def prewarm_pool(self) -> None:
        """Pre-warm the connection pool by creating connections up to max_size."""
        current_size = len(self.pool)
        if current_size < CONNECTION_POOL_MAX_SIZE:
            # Create connections to fill the pool
            connections_to_create = CONNECTION_POOL_MAX_SIZE - current_size
            self.logger.debug(f"Pre-warming pool with {connections_to_create} connections")

            for _ in range(connections_to_create):
                try:
                    conn = await self._create_connection()
                    # Check if connection is healthy before adding to pool
                    if await conn.is_healthy():
                        self.pool.append(conn)
                    else:
                        await conn.close()
                except Exception as e:
                    self.logger.debug(f"Failed to create connection during pre-warm: {e}")
                    break  # Stop trying if we can't connect
