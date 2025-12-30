# type: ignore
"""Tests for notification processing."""

import logging

import pytest

from pymadvr.notifications import NotificationProcessor


@pytest.fixture
def processor():
    """Create a NotificationProcessor instance for testing."""
    return NotificationProcessor(logging.getLogger())


@pytest.mark.asyncio
async def test_standby_notification_single_word(processor):
    """Test that single-word Standby notification is processed correctly."""
    result = await processor.process_notifications("Standby\r\n")

    assert result.get("is_on") is False
    assert result.get("power_off") is True
    assert result.get("standby") is True


@pytest.mark.asyncio
async def test_poweroff_notification_single_word(processor):
    """Test that single-word PowerOff notification is processed correctly."""
    result = await processor.process_notifications("PowerOff\r\n")

    assert result.get("is_on") is False
    assert result.get("power_off") is True
    # PowerOff should not set standby flag
    assert result.get("standby") is None


@pytest.mark.asyncio
async def test_reset_temporary_notification(processor):
    """Test that ResetTemporary notification is handled without error."""
    result = await processor.process_notifications("ResetTemporary\r\n")

    # Should not crash, just returns empty dict (no specific data to extract)
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_nosignal_notification(processor):
    """Test that NoSignal notification is processed correctly."""
    result = await processor.process_notifications("NoSignal\r\n")

    assert result.get("is_signal") is False


@pytest.mark.asyncio
async def test_multiple_notifications_including_standby(processor):
    """Test processing multiple notifications including Standby."""
    msg = "Standby\r\nResetTemporary\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("is_on") is False
    assert result.get("power_off") is True
    assert result.get("standby") is True


@pytest.mark.asyncio
async def test_notification_with_ok_response(processor):
    """Test that OK response is ignored but other notifications processed."""
    msg = "OK\r\nStandby\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("is_on") is False
    assert result.get("power_off") is True


@pytest.mark.asyncio
async def test_incoming_signal_info(processor):
    """Test that IncomingSignalInfo notification with parameters is processed."""
    msg = "IncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("incoming_res") == "3840x2160"
    assert result.get("incoming_frame_rate") == "23.976p"
    assert result.get("incoming_signal_type") == "2D"
    assert result.get("incoming_color_space") == "422"
    assert result.get("incoming_bit_depth") == "10bit"
    assert result.get("hdr_flag") is True
    assert result.get("incoming_colorimetry") == "2020"
    assert result.get("incoming_black_levels") == "TV"
    assert result.get("incoming_aspect_ratio") == "16:9"
    assert result.get("is_signal") is True


@pytest.mark.asyncio
async def test_outgoing_signal_info(processor):
    """Test that OutgoingSignalInfo notification with parameters is processed."""
    msg = "OutgoingSignalInfo 3840x2160 23.976p 2D RGB 12bit SDR 2020 TV\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("outgoing_res") == "3840x2160"
    assert result.get("outgoing_frame_rate") == "23.976p"
    assert result.get("outgoing_signal_type") == "2D"
    assert result.get("outgoing_color_space") == "RGB"
    assert result.get("outgoing_bit_depth") == "12bit"
    assert result.get("outgoing_hdr_flag") is False
    assert result.get("outgoing_colorimetry") == "2020"
    assert result.get("outgoing_black_levels") == "TV"


@pytest.mark.asyncio
async def test_temperatures_notification(processor):
    """Test that Temperatures notification is processed correctly."""
    msg = "Temperatures 74 67 41 45\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("temp_gpu") == "74"
    assert result.get("temp_hdmi") == "67"
    assert result.get("temp_cpu") == "41"
    assert result.get("temp_mainboard") == "45"


@pytest.mark.asyncio
async def test_mac_address_notification(processor):
    """Test that MacAddress notification is processed correctly."""
    msg = "MacAddress 01-02-03-04-05-06\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("mac_address") == "01-02-03-04-05-06"


@pytest.mark.asyncio
async def test_aspect_ratio_notification(processor):
    """Test that AspectRatio notification is processed correctly."""
    msg = 'AspectRatio 3840:1600 2.400 240 "Panavision"\r\n'
    result = await processor.process_notifications(msg)

    assert result.get("aspect_res") == "3840:1600"
    assert result.get("aspect_dec") == 2.400
    assert result.get("aspect_int") == "240"
    assert result.get("aspect_name") == '"Panavision"'


@pytest.mark.asyncio
async def test_masking_ratio_notification(processor):
    """Test that MaskingRatio notification is processed correctly."""
    msg = "MaskingRatio 3840:1700 2.259 220\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("masking_res") == "3840:1700"
    assert result.get("masking_dec") == 2.259
    assert result.get("masking_int") == "220"


@pytest.mark.asyncio
async def test_activate_profile_notification(processor):
    """Test that ActivateProfile notification is processed correctly."""
    msg = "ActivateProfile SOURCE 2\r\n"
    result = await processor.process_notifications(msg)

    assert result.get("profile_name") == "SOURCE"
    assert result.get("profile_num") == "2"


@pytest.mark.asyncio
async def test_empty_notification_ignored(processor):
    """Test that empty notifications are ignored."""
    result = await processor.process_notifications("\r\n")

    assert result == {}


@pytest.mark.asyncio
async def test_unknown_single_word_notification_ignored(processor):
    """Test that unknown single-word notifications are ignored (no crash)."""
    result = await processor.process_notifications("UnknownNotification\r\n")

    # Should not crash, just returns empty dict
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_clear_state(processor):
    """Test that clear_state clears the internal message dictionary."""
    # First process some data
    await processor.process_notifications("Temperatures 74 67 41 45\r\n")
    assert processor.msg_dict.get("temp_gpu") == "74"

    # Clear state
    processor.clear_state()

    assert processor.msg_dict == {}


@pytest.mark.asyncio
async def test_process_notifications_sets_standby_in_msg_dict():
    """Test that _process_notifications sets standby in msg_dict for HA coordinator."""
    from unittest.mock import AsyncMock, patch

    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")
        madvr._handle_power_off = AsyncMock()

        await madvr._process_notifications("Standby\r\n")

        assert madvr.msg_dict.get("standby") is True
        madvr._handle_power_off.assert_called_once_with(is_standby=True)


@pytest.mark.asyncio
async def test_process_notifications_sets_standby_false_for_poweroff():
    """Test that _process_notifications sets standby=False for PowerOff notification."""
    from unittest.mock import AsyncMock, patch

    from pymadvr.madvr import Madvr

    with patch("pymadvr.madvr.asyncio.open_connection", new_callable=AsyncMock):
        madvr = Madvr("192.168.1.100")
        madvr._handle_power_off = AsyncMock()

        await madvr._process_notifications("PowerOff\r\n")

        assert madvr.msg_dict.get("standby") is False
        madvr._handle_power_off.assert_called_once_with(is_standby=False)
