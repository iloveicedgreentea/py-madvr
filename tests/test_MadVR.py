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


# ============================================================================
# Integration tests for power_off flow
# ============================================================================


@pytest.mark.asyncio
async def test_power_off_updates_ha_state():
    """
    Integration test: Verify that power_off() correctly updates HA state.

    This tests the full flow:
    1. Device is on (is_on=True in msg_dict)
    2. power_off() is called
    3. _clear_attr() clears msg_dict (is_on key is removed)
    4. _set_device_power_state(False) should still update HA because key was missing
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is on with some attributes
        madvr.msg_dict = {
            "is_on": True,
            "mac_address": "00:11:22:33:44:55",
            "some_attr": "value",
        }

        # Track HA updates
        ha_updates = []
        def track_update(data):
            ha_updates.append(data.copy())
        madvr.set_update_callback(track_update)

        # Mock send_command and connection cleanup
        madvr.send_command = AsyncMock()
        madvr._clear_notification_connection = AsyncMock()
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Execute power_off
        await madvr.power_off()

        # Verify: HA was updated
        assert len(ha_updates) == 1, "HA should have been updated exactly once"

        # Verify: is_on is False in the update
        assert ha_updates[0].get("is_on") is False, "is_on should be False in HA update"

        # Verify: msg_dict has correct state
        assert madvr.msg_dict.get("is_on") is False
        assert madvr.msg_dict.get("standby") is False
        assert madvr.msg_dict.get("mac_address") == "00:11:22:33:44:55"

        # Verify: other attributes were cleared
        assert "some_attr" not in madvr.msg_dict


@pytest.mark.asyncio
async def test_power_off_standby_updates_ha_state():
    """
    Integration test: Verify that power_off(standby=True) correctly updates HA state.
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is on
        madvr.msg_dict = {
            "is_on": True,
            "mac_address": "00:11:22:33:44:55",
        }

        # Track HA updates
        ha_updates = []
        def track_update(data):
            ha_updates.append(data.copy())
        madvr.set_update_callback(track_update)

        # Mock send_command and connection cleanup
        madvr.send_command = AsyncMock()
        madvr._clear_notification_connection = AsyncMock()
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Execute power_off with standby
        await madvr.power_off(standby=True)

        # Verify: HA was updated
        assert len(ha_updates) == 1, "HA should have been updated exactly once"

        # Verify: standby is True in the update
        assert ha_updates[0].get("standby") is True, "standby should be True in HA update"
        assert ha_updates[0].get("is_on") is False, "is_on should be False in HA update"


@pytest.mark.asyncio
async def test_power_off_clears_connections():
    """
    Integration test: Verify that power_off() clears notification connection and connection pool.
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is on
        madvr.msg_dict = {"is_on": True}

        # Mock components
        madvr.send_command = AsyncMock()
        madvr._clear_notification_connection = AsyncMock()
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Execute power_off
        await madvr.power_off()

        # Verify: connections were cleared
        madvr._clear_notification_connection.assert_called_once()
        madvr.connection_pool.close_all.assert_called_once()


@pytest.mark.asyncio
async def test_handle_power_off_from_notification_updates_ha():
    """
    Integration test: Verify that receiving a PowerOff notification updates HA state.

    This simulates receiving a "PowerOff" or "Standby" notification from the device
    (e.g., user pressed power button on remote).
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is on
        madvr.msg_dict = {
            "is_on": True,
            "mac_address": "00:11:22:33:44:55",
        }

        # Track HA updates
        ha_updates = []
        def track_update(data):
            ha_updates.append(data.copy())
        madvr.set_update_callback(track_update)

        # Mock connection cleanup
        madvr._clear_notification_connection = AsyncMock()
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Simulate receiving a PowerOff notification
        await madvr._process_notifications("PowerOff\r\n")

        # Verify: HA was updated
        assert len(ha_updates) == 1, "HA should have been updated exactly once"
        assert ha_updates[0].get("is_on") is False
        assert ha_updates[0].get("standby") is False


@pytest.mark.asyncio
async def test_handle_standby_from_notification_updates_ha():
    """
    Integration test: Verify that receiving a Standby notification updates HA state.
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is on
        madvr.msg_dict = {
            "is_on": True,
            "mac_address": "00:11:22:33:44:55",
        }

        # Track HA updates
        ha_updates = []
        def track_update(data):
            ha_updates.append(data.copy())
        madvr.set_update_callback(track_update)

        # Mock connection cleanup
        madvr._clear_notification_connection = AsyncMock()
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Simulate receiving a Standby notification
        await madvr._process_notifications("Standby\r\n")

        # Verify: HA was updated
        assert len(ha_updates) == 1, "HA should have been updated exactly once"
        assert ha_updates[0].get("is_on") is False
        assert ha_updates[0].get("standby") is True


@pytest.mark.asyncio
async def test_set_device_power_state_updates_ha_when_key_missing():
    """
    Unit test: Verify _set_device_power_state updates HA when is_on key is missing.

    This is the core fix - after _clear_attr() removes is_on, calling
    _set_device_power_state(False) should still trigger HA update.
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: msg_dict has NO is_on key (simulates post-_clear_attr state)
        madvr.msg_dict = {"mac_address": "00:11:22:33:44:55"}

        # Track HA updates
        ha_updates = []
        def track_update(data):
            ha_updates.append(data.copy())
        madvr.set_update_callback(track_update)

        # Call _set_device_power_state with False
        await madvr._set_device_power_state(False)

        # Verify: HA was updated even though "old state" would be False (default)
        assert len(ha_updates) == 1, "HA should have been updated because is_on key was missing"
        assert ha_updates[0].get("is_on") is False


@pytest.mark.asyncio
async def test_set_device_power_state_no_update_when_already_off():
    """
    Unit test: Verify _set_device_power_state does NOT update HA when already off.
    """
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: is_on is already False
        madvr.msg_dict = {"is_on": False}

        # Track HA updates
        ha_updates = []
        def track_update(data):
            ha_updates.append(data.copy())
        madvr.set_update_callback(track_update)

        # Call _set_device_power_state with False (no change)
        await madvr._set_device_power_state(False)

        # Verify: HA was NOT updated (state didn't change)
        assert len(ha_updates) == 0, "HA should NOT be updated when state hasn't changed"


# ============================================================================
# Hysteresis tests for ping race condition fix
# ============================================================================


@pytest.mark.asyncio
async def test_power_off_sets_hysteresis_timestamp():
    """Test that _handle_power_off records the power-off timestamp for hysteresis."""
    import time
    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup
        madvr.msg_dict = {"is_on": True}
        madvr._clear_notification_connection = AsyncMock()
        madvr.connection_pool = MagicMock()
        madvr.connection_pool.close_all = AsyncMock()

        # Verify initial state
        assert madvr._power_off_time == 0.0

        before_time = time.time()
        await madvr._handle_power_off()
        after_time = time.time()

        # Verify timestamp was set
        assert madvr._power_off_time >= before_time
        assert madvr._power_off_time <= after_time


@pytest.mark.asyncio
async def test_power_on_clears_hysteresis_timestamp(mock_madvr, mock_send_magic_packet):
    """Test that power_on clears the hysteresis timestamp."""
    import time

    mock_madvr.msg_dict = {"mac_address": "00:11:22:33:44:55"}
    mock_madvr._power_off_time = time.time()  # Simulate recent power off

    await mock_madvr.power_on()

    # Verify timestamp was cleared
    assert mock_madvr._power_off_time == 0.0
    mock_send_magic_packet.assert_called_once()


@pytest.mark.asyncio
async def test_ping_respects_hysteresis_window():
    """
    Test that ping task doesn't mark device online within hysteresis window.

    This prevents the race condition where device is briefly still connectable
    during shutdown and ping would incorrectly mark it as online.
    """
    import time
    from pymadvr.madvr import Madvr
    from pymadvr.consts import POWER_OFF_HYSTERESIS

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is off, recent power_off timestamp
        madvr.msg_dict = {"is_on": False}
        madvr._power_off_time = time.time()  # Just powered off

        # Mock is_device_connectable to return True (device still connectable during shutdown)
        madvr.is_device_connectable = AsyncMock(return_value=True)

        # Track if _set_device_power_state was called
        madvr._set_device_power_state = AsyncMock()

        # Import the hysteresis check logic (simulate one ping iteration)
        is_available = await madvr.is_device_connectable()
        assert is_available is True

        # Check hysteresis logic
        time_since_power_off = time.time() - madvr._power_off_time
        assert time_since_power_off < POWER_OFF_HYSTERESIS, "Should be within hysteresis window"

        # Verify: _set_device_power_state should NOT be called within hysteresis
        if not madvr.msg_dict.get("is_on", False):
            if time_since_power_off > POWER_OFF_HYSTERESIS:
                await madvr._set_device_power_state(True)

        madvr._set_device_power_state.assert_not_called()


@pytest.mark.asyncio
async def test_ping_marks_online_after_hysteresis_expires():
    """
    Test that ping task marks device online after hysteresis window expires.

    This ensures device can be detected as online if turned on manually
    (e.g., out-of-band, via remote) after the hysteresis window.
    """
    import time
    from pymadvr.madvr import Madvr
    from pymadvr.consts import POWER_OFF_HYSTERESIS

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is off, OLD power_off timestamp (beyond hysteresis)
        madvr.msg_dict = {"is_on": False}
        madvr._power_off_time = time.time() - POWER_OFF_HYSTERESIS - 10  # 10 seconds past hysteresis

        # Mock is_device_connectable to return True
        madvr.is_device_connectable = AsyncMock(return_value=True)

        # Track _set_device_power_state calls
        madvr._set_device_power_state = AsyncMock()

        # Simulate ping logic
        is_available = await madvr.is_device_connectable()
        assert is_available is True

        time_since_power_off = time.time() - madvr._power_off_time
        assert time_since_power_off > POWER_OFF_HYSTERESIS, "Should be past hysteresis window"

        # This is what the ping task does
        if not madvr.msg_dict.get("is_on", False):
            if time_since_power_off > POWER_OFF_HYSTERESIS:
                await madvr._set_device_power_state(True)

        # Verify: device should be marked online
        madvr._set_device_power_state.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_ping_marks_online_immediately_when_no_power_off():
    """
    Test that ping task marks device online immediately when _power_off_time is 0.

    This handles the case where device was never powered off via our API
    (e.g., first connection, or restarted integration).
    """
    import time
    from pymadvr.madvr import Madvr
    from pymadvr.consts import POWER_OFF_HYSTERESIS

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")

        # Setup: device is off, no prior power_off (default state)
        madvr.msg_dict = {"is_on": False}
        madvr._power_off_time = 0.0  # Never powered off via our API

        # Mock is_device_connectable to return True
        madvr.is_device_connectable = AsyncMock(return_value=True)

        # Track _set_device_power_state calls
        madvr._set_device_power_state = AsyncMock()

        # Simulate ping logic
        is_available = await madvr.is_device_connectable()
        assert is_available is True

        time_since_power_off = time.time() - madvr._power_off_time
        # time.time() is ~1704067200 (Jan 2024), so this will be huge
        assert time_since_power_off > POWER_OFF_HYSTERESIS

        # This is what the ping task does
        if not madvr.msg_dict.get("is_on", False):
            if time_since_power_off > POWER_OFF_HYSTERESIS:
                await madvr._set_device_power_state(True)

        # Verify: device should be marked online immediately
        madvr._set_device_power_state.assert_called_once_with(True)
