# type: ignore
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from madvr.madvr import Madvr


@pytest.fixture
def mock_madvr():
    with patch("madvr.madvr.asyncio.open_connection", new_callable=AsyncMock), patch(
        "madvr.madvr.Madvr.connected", new_callable=PropertyMock, return_value=True
    ):
        madvr = Madvr("192.168.1.100")
        # ignore mypy
        #
        madvr.writer = AsyncMock()
        madvr.reader = AsyncMock()
        madvr._set_connected = AsyncMock()
        madvr._clear_attr = AsyncMock()
        madvr.is_device_connectable = AsyncMock()
        madvr.close_connection = AsyncMock()
        madvr._construct_command = AsyncMock()
        madvr._write_with_timeout = AsyncMock()
        madvr.stop = MagicMock()
        madvr.stop_commands_flag = MagicMock()
        madvr.stop_heartbeat = MagicMock()
        madvr.add_command_to_queue = AsyncMock()
        madvr._reconnect = AsyncMock()
        madvr._write_with_timeout = AsyncMock()

        # Mock the background tasks to prevent warnings
        madvr.task_handle_queue = AsyncMock()
        madvr.task_read_notifications = AsyncMock()
        # madvr.send_heartbeat = AsyncMock()
        madvr.task_ping_until_alive = AsyncMock()
        madvr.task_refresh_info = AsyncMock()
        yield madvr


@pytest.fixture
def mock_send_magic_packet():
    with patch("madvr.madvr.send_magic_packet") as mock:
        yield mock


@pytest.fixture
def mock_wait_for():
    async def mock_wait_for_func(coro, timeout):
        return await coro

    with patch("asyncio.wait_for", mock_wait_for_func):
        yield
