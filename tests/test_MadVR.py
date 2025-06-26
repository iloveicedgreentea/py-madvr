# type: ignore
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_init(mock_madvr):
    assert mock_madvr.host == "192.168.1.100"
    assert mock_madvr.port == 44077  # Assuming DEFAULT_PORT is 44077
    assert mock_madvr.connection_pool is not None


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
        assert mock_madvr.notification_task is not None
        assert mock_madvr.ping_task is not None
        assert mock_madvr.refresh_task is not None
        assert mock_madvr.queue_task is not None  # 4 tasks: notifications, ping, refresh, and queue


@pytest.mark.asyncio
async def test_send_command(mock_madvr):
    # Mock connection pool's send_command method
    mock_madvr.connection_pool.send_command = AsyncMock(return_value="OK")
    mock_madvr._construct_command = AsyncMock(return_value=(b"TestCommand\r\n", "enum_type"))

    result = await mock_madvr.send_command(["TestCommand"])

    mock_madvr._construct_command.assert_called_once_with(["TestCommand"])
    mock_madvr.connection_pool.send_command.assert_called_once_with(b"TestCommand\r\n")
    assert result == "OK"


@pytest.mark.asyncio
async def test_send_command_error(mock_madvr):
    # Mock connection pool's send_command to raise error
    mock_madvr.connection_pool.send_command = AsyncMock(side_effect=ConnectionError("Test error"))
    mock_madvr._construct_command = AsyncMock(return_value=(b"TestCommand\r\n", "enum_type"))

    with pytest.raises(ConnectionError):
        await mock_madvr.send_command(["TestCommand"])


@pytest.mark.asyncio
async def test_open_connection(mock_madvr):
    # Mock notification connection setup
    mock_madvr._establish_notification_connection = AsyncMock()
    mock_madvr.async_add_tasks = AsyncMock()
    mock_madvr._get_initial_device_info = AsyncMock()

    await mock_madvr.open_connection()

    mock_madvr._establish_notification_connection.assert_called_once()
    mock_madvr.async_add_tasks.assert_called_once()
    mock_madvr._get_initial_device_info.assert_called_once()


@pytest.mark.asyncio
async def test_open_connection_error(mock_madvr):
    mock_madvr._establish_notification_connection = AsyncMock(side_effect=ConnectionError("Test error"))

    with pytest.raises(ConnectionError):
        await mock_madvr.open_connection()

    mock_madvr._establish_notification_connection.assert_called_once()


@pytest.mark.asyncio
async def test_power_on(mock_madvr, mock_send_magic_packet):
    mock_madvr.msg_dict = {"mac_address": "00:11:22:33:44:55"}
    mock_madvr.stop_commands_flag = MagicMock()
    mock_madvr.stop_commands_flag.is_set.return_value = False

    await mock_madvr.power_on()

    mock_send_magic_packet.assert_called_once_with("00:11:22:33:44:55", logger=mock_madvr.logger)


@pytest.mark.asyncio
async def test_power_off(mock_madvr):
    # Mock send_command to avoid actual connection
    mock_madvr.send_command = AsyncMock()

    await mock_madvr.power_off()

    mock_madvr.stop.assert_called_once()
    assert mock_madvr.powered_off_recently is True
    mock_madvr.send_command.assert_called_once_with(["PowerOff"])
    mock_madvr.close_connection.assert_called_once()


@pytest.mark.asyncio
async def test_power_off_standby(mock_madvr):
    # Mock send_command to avoid actual connection
    mock_madvr.send_command = AsyncMock()

    await mock_madvr.power_off(standby=True)

    mock_madvr.stop.assert_called_once()
    assert mock_madvr.powered_off_recently is True
    mock_madvr.send_command.assert_called_once_with(["Standby"])
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
