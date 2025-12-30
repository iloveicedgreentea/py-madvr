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
    # Mock the background tasks setup
    mock_madvr.async_add_tasks = AsyncMock()
    mock_madvr._get_initial_device_info = AsyncMock()
    # Set notification_connected so open_connection doesn't timeout
    mock_madvr.notification_connected.set()

    await mock_madvr.open_connection()

    # Verify tasks were started and initial info was fetched
    mock_madvr.async_add_tasks.assert_called_once()
    mock_madvr._get_initial_device_info.assert_called_once()


@pytest.mark.asyncio
async def test_open_connection_error(mock_madvr):
    # Mock async_add_tasks to raise an error
    mock_madvr.async_add_tasks = AsyncMock(side_effect=ConnectionError("Test error"))

    with pytest.raises(ConnectionError):
        await mock_madvr.open_connection()


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
    mock_madvr._clear_attr = AsyncMock()
    mock_madvr._set_device_power_state = AsyncMock()

    await mock_madvr.power_off()

    mock_madvr.send_command.assert_called_once_with(["PowerOff"])
    mock_madvr._clear_attr.assert_called_once()
    mock_madvr._set_device_power_state.assert_called_once_with(False)
    # Verify standby flag is not set for regular power off
    assert mock_madvr._is_standby is False


@pytest.mark.asyncio
async def test_power_off_standby(mock_madvr):
    # Mock send_command to avoid actual connection
    mock_madvr.send_command = AsyncMock()
    mock_madvr._clear_attr = AsyncMock()
    mock_madvr._set_device_power_state = AsyncMock()

    await mock_madvr.power_off(standby=True)

    mock_madvr.send_command.assert_called_once_with(["Standby"])
    mock_madvr._clear_attr.assert_called_once()
    mock_madvr._set_device_power_state.assert_called_once_with(False)
    # Verify standby flag is set
    assert mock_madvr._is_standby is True


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


@pytest.mark.asyncio
async def test_is_standby_property(mock_madvr):
    """Test that is_standby property reflects the internal state."""
    mock_madvr._is_standby = False
    assert mock_madvr.is_standby is False

    mock_madvr._is_standby = True
    assert mock_madvr.is_standby is True


@pytest.mark.asyncio
async def test_power_on_clears_standby_flag(mock_madvr, mock_send_magic_packet):
    """Test that power_on clears the standby flag."""
    mock_madvr._is_standby = True
    mock_madvr.msg_dict = {"mac_address": "00:11:22:33:44:55"}

    await mock_madvr.power_on()

    assert mock_madvr._is_standby is False
    mock_send_magic_packet.assert_called_once()


@pytest.mark.asyncio
async def test_handle_power_off_sets_standby_flag(mock_madvr):
    """Test that _handle_power_off sets standby flag when is_standby=True."""
    mock_madvr._is_standby = False
    mock_madvr._clear_attr = AsyncMock()
    mock_madvr._set_device_power_state = AsyncMock()

    await mock_madvr._handle_power_off(is_standby=True)

    assert mock_madvr._is_standby is True
    mock_madvr._clear_attr.assert_called_once()
    mock_madvr._set_device_power_state.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_handle_power_off_clears_standby_flag(mock_madvr):
    """Test that _handle_power_off clears standby flag when is_standby=False."""
    mock_madvr._is_standby = True
    mock_madvr._clear_attr = AsyncMock()
    mock_madvr._set_device_power_state = AsyncMock()

    await mock_madvr._handle_power_off(is_standby=False)

    assert mock_madvr._is_standby is False
    mock_madvr._clear_attr.assert_called_once()
    mock_madvr._set_device_power_state.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_power_off_sets_standby_in_msg_dict(mock_madvr):
    """Test that power_off(standby=True) sets standby in msg_dict for HA coordinator."""
    mock_madvr.send_command = AsyncMock()
    mock_madvr._clear_attr = AsyncMock()
    mock_madvr._set_device_power_state = AsyncMock()

    await mock_madvr.power_off(standby=True)

    assert mock_madvr.msg_dict.get("standby") is True


@pytest.mark.asyncio
async def test_power_off_clears_standby_in_msg_dict(mock_madvr):
    """Test that regular power_off sets standby=False in msg_dict."""
    mock_madvr.send_command = AsyncMock()
    mock_madvr._clear_attr = AsyncMock()
    mock_madvr._set_device_power_state = AsyncMock()
    mock_madvr.msg_dict["standby"] = True  # Previously in standby

    await mock_madvr.power_off(standby=False)

    assert mock_madvr.msg_dict.get("standby") is False


@pytest.mark.asyncio
async def test_power_on_clears_standby_in_msg_dict(mock_madvr, mock_send_magic_packet):
    """Test that power_on clears standby in msg_dict."""
    mock_madvr.msg_dict = {"mac_address": "00:11:22:33:44:55", "standby": True}

    await mock_madvr.power_on()

    assert mock_madvr.msg_dict.get("standby") is False
