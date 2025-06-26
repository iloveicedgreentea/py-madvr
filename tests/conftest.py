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

        # Mock connection pool
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.get_connection = AsyncMock()
        madvr.connection_pool.return_connection = AsyncMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Mock notification connection components
        madvr.notification_reader = AsyncMock()
        madvr.notification_writer = AsyncMock()
        madvr.notification_task = MagicMock()
        madvr.ping_task = MagicMock()
        madvr.refresh_task = MagicMock()
        madvr.queue_task = MagicMock()

        # Mock methods
        madvr._set_connected = AsyncMock()
        madvr._clear_attr = AsyncMock()
        madvr.is_device_connectable = AsyncMock()
        madvr.close_connection = AsyncMock()
        madvr._construct_command = AsyncMock()
        madvr.stop = MagicMock()
        madvr.add_command_to_queue = AsyncMock()
        madvr._establish_notification_connection = AsyncMock()
        madvr._get_initial_device_info = AsyncMock()

        # Mock the background tasks
        madvr.task_read_notifications = AsyncMock()
        madvr.task_refresh_info = AsyncMock()
        madvr.task_process_command_queue = AsyncMock()
        yield madvr


@pytest.fixture
def mock_send_magic_packet():
    with patch("madvr.madvr.send_magic_packet") as mock:
        yield mock


@pytest.fixture
def mock_wait_for():
    async def mock_wait_for_func(coro, timeout):  # noqa: ARG001
        return await coro

    with patch("asyncio.wait_for", mock_wait_for_func):
        yield
