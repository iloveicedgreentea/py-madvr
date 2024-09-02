# type: ignore
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madvr.errors import HeartBeatError


@pytest.mark.asyncio
async def test_init(mock_madvr):
    assert mock_madvr.host == "192.168.1.100"
    assert mock_madvr.port == 44077  # Assuming DEFAULT_PORT is 44077
    assert isinstance(mock_madvr.command_queue, asyncio.Queue)


@pytest.mark.asyncio
async def test_is_on_property(mock_madvr):
    mock_madvr.msg_dict = {"is_on": True}
    assert mock_madvr.is_on is True

    mock_madvr.msg_dict = {"is_on": False}
    assert mock_madvr.is_on is False


@pytest.mark.asyncio
async def test_mac_address_property(mock_madvr):
    mock_madvr.msg_dict = {"mac_address": "00:11:22:33:44:55"}
    assert mock_madvr.mac_address == "00:11:22:33:44:55"

    mock_madvr.msg_dict = {}
    assert mock_madvr.mac_address == ""


@pytest.mark.asyncio
async def test_set_update_callback(mock_madvr):
    callback = MagicMock()
    mock_madvr.set_update_callback(callback)
    assert mock_madvr.update_callback == callback


@pytest.mark.asyncio
async def test_async_add_tasks(mock_madvr):
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.create_task = AsyncMock()
        await mock_madvr.async_add_tasks()
        assert len(mock_madvr.tasks) == 5  # Assuming 5 tasks are created


@pytest.mark.asyncio
async def test_send_heartbeat(mock_madvr):
    await mock_madvr.send_heartbeat(once=True)
    mock_madvr._write_with_timeout.assert_called_once_with(mock_madvr.HEARTBEAT)


@pytest.mark.asyncio
async def test_send_heartbeat_error(mock_madvr):
    mock_madvr._write_with_timeout = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(HeartBeatError):
        await mock_madvr.send_heartbeat(once=True)


@pytest.mark.asyncio
async def test_open_connection(mock_madvr):
    await mock_madvr.open_connection()

    mock_madvr._reconnect.assert_called_once()
    assert mock_madvr.add_command_to_queue.call_count == 5


@pytest.mark.asyncio
async def test_open_connection_error(mock_madvr):
    mock_madvr._reconnect.side_effect = ConnectionError

    with pytest.raises(ConnectionError):
        await mock_madvr.open_connection()

    mock_madvr.add_command_to_queue.assert_not_called()


@pytest.mark.asyncio
async def test_power_on(mock_madvr, mock_send_magic_packet):
    mock_madvr.msg_dict = {"mac_address": "00:11:22:33:44:55"}
    mock_madvr.stop_commands_flag = MagicMock()
    mock_madvr.stop_commands_flag.is_set.return_value = False

    await mock_madvr.power_on()

    mock_send_magic_packet.assert_called_once_with("00:11:22:33:44:55", logger=mock_madvr.logger)


@pytest.mark.asyncio
async def test_power_off(mock_madvr):
    mock_madvr._construct_command.return_value = (b"PowerOff\r", "enum_type")

    await mock_madvr.power_off()

    mock_madvr.stop.assert_called_once()
    assert mock_madvr.powered_off_recently is True
    mock_madvr._construct_command.assert_called_once_with(["PowerOff"])
    mock_madvr._write_with_timeout.assert_called_once_with(b"PowerOff\r")
    mock_madvr.close_connection.assert_called_once()


@pytest.mark.asyncio
async def test_power_off_standby(mock_madvr):
    mock_madvr._construct_command.return_value = (b"Standby\r", "enum_type")

    await mock_madvr.power_off(standby=True)

    mock_madvr.stop.assert_called_once()
    assert mock_madvr.powered_off_recently is True
    mock_madvr._construct_command.assert_called_once_with(["Standby"])
    mock_madvr._write_with_timeout.assert_called_once_with(b"Standby\r")
    mock_madvr.close_connection.assert_called_once()


# Add more tests as needed for other methods and edge cases
