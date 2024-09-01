from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from madvr.madvr import Madvr
import math



@pytest.fixture
def mock_madvr():
    with patch("madvr.madvr.asyncio.open_connection", new_callable=AsyncMock), patch(
        "madvr.madvr.Madvr.connected", new_callable=PropertyMock, return_value=True
    ):

        madvr = Madvr("192.168.1.100") #f.                                                             #.                              
        madvr.writer = AsyncMock()
        madvr.reader = AsyncMock()
        madvr._set_connected = AsyncMock()
        madvr._clear_attr = AsyncMock()
        madvr.is_device_connectable = AsyncMock()
        madvr.open_connection = AsyncMock()
        madvr.close_connection = AsyncMock()
        madvr._construct_command = AsyncMock()  # Mock this method
        madvr._send_command = AsyncMock()
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
