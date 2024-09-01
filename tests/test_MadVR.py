import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from madvr.madvr import Madvr, COMMAND_TIMEOUT, CONNECT_TIMEOUT, DEFAULT_PORT
from madvr.errors import AckError, HeartBeatError, RetryExceededError

@pytest.mark.asyncio
async def test_init(mock_madvr):
    assert mock_madvr.host == "192.168.1.100"
    assert mock_madvr.port == DEFAULT_PORT
    assert mock_madvr.connect_timeout == CONNECT_TIMEOUT
    assert mock_madvr.command_read_timeout == COMMAND_TIMEOUT

@pytest.mark.asyncio
async def test_is_on(mock_madvr):
    mock_madvr.msg_dict["is_on"] = True
    assert mock_madvr.is_on == True

@pytest.mark.asyncio
async def test_mac_address(mock_madvr):
    mock_madvr.msg_dict["mac_address"] = "00:11:22:33:44:55"
    assert mock_madvr.mac_address == "00:11:22:33:44:55"

@pytest.mark.asyncio
async def test_set_update_callback(mock_madvr):
    callback = MagicMock()
    mock_madvr.set_update_callback(callback)
    assert mock_madvr.update_callback == callback

@pytest.mark.asyncio
async def test_send_heartbeat(mock_madvr):
    mock_madvr.connection_event.set()
    
    await mock_madvr.send_heartbeat(once=True)
    
    mock_madvr.writer.write.assert_called_once_with(mock_madvr.HEARTBEAT)
    mock_madvr.writer.drain.assert_called_once()


@pytest.mark.asyncio
async def test_add_command_to_queue(mock_madvr):
    command = ["TestCommand"]
    await mock_madvr.add_command_to_queue(command)
    assert mock_madvr.command_queue.get_nowait() == command
