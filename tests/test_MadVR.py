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
        mock_task = MagicMock()
        mock_task.set_name = MagicMock()
        mock_loop.return_value.create_task = MagicMock(return_value=mock_task)
        await mock_madvr.async_add_tasks()
        assert len(mock_madvr.tasks) == 5  # Assuming 5 tasks are created


@pytest.mark.asyncio
async def test_send_heartbeat(mock_madvr):
    # Set up the writer mock properly
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_madvr.writer = mock_writer

    # Create a proper async context manager mock
    async_lock_mock = AsyncMock()
    async_lock_mock.__aenter__ = AsyncMock(return_value=None)
    async_lock_mock.__aexit__ = AsyncMock(return_value=None)
    mock_madvr.lock = async_lock_mock

    await mock_madvr.send_heartbeat(once=True)
    mock_writer.write.assert_called_once_with(mock_madvr.HEARTBEAT)


@pytest.mark.asyncio
async def test_send_heartbeat_error(mock_madvr):
    # Set up the writer mock to raise an error
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock(side_effect=ConnectionError("Test error"))
    mock_madvr.writer = mock_writer

    # Create a proper async context manager mock
    async_lock_mock = AsyncMock()
    async_lock_mock.__aenter__ = AsyncMock(return_value=None)
    async_lock_mock.__aexit__ = AsyncMock(return_value=None)
    mock_madvr.lock = async_lock_mock

    with pytest.raises(HeartBeatError):
        await mock_madvr.send_heartbeat(once=True)


@pytest.mark.asyncio
async def test_open_connection(mock_madvr):
    await mock_madvr.open_connection()

    mock_madvr._reconnect.assert_called_once()
    # Updated to match the new reduced command count (3 instead of 5)
    assert mock_madvr.add_command_to_queue.call_count == 3


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


@pytest.mark.asyncio
async def test_display_message(mock_madvr):
    await mock_madvr.display_message(5, "Test message")
    mock_madvr.add_command_to_queue.assert_called_once_with(["DisplayMessage", "5", '"Test message"'])


@pytest.mark.asyncio
async def test_display_audio_volume(mock_madvr):
    await mock_madvr.display_audio_volume(0, 50, 100, "%")
    mock_madvr.add_command_to_queue.assert_called_once_with(["DisplayAudioVolume", "0", "50", "100", '"%"'])


@pytest.mark.asyncio
async def test_display_audio_mute(mock_madvr):
    await mock_madvr.display_audio_mute()
    mock_madvr.add_command_to_queue.assert_called_once_with(["DisplayAudioMute"])


@pytest.mark.asyncio
async def test_close_audio_mute(mock_madvr):
    await mock_madvr.close_audio_mute()
    mock_madvr.add_command_to_queue.assert_called_once_with(["CloseAudioMute"])
