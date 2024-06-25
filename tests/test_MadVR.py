# test_madvr.py

import pytest
import asyncio
import pytest_asyncio
from madvr.madvr import Madvr


@pytest_asyncio.fixture(scope="session")
async def madvr_instance():
    print("Creating MadVR instance")
    madvr = Madvr(host="192.168.88.38", port=44077)
    await madvr.open_connection()
    print("Madvr instance created")
    yield madvr
    print("Closing MadVR instance")
    madvr.stop()
    await madvr.close_connection()
    madvr.ping_task.cancel()


@pytest.mark.asyncio(scope="session")
async def test_open_connection(madvr_instance):
    assert madvr_instance.connected() is True
    print("Connection opened")


# @pytest.mark.asyncio
# async def test_close_connection(madvr_instance):
#     await madvr_instance.close_connection()
#     assert madvr_instance.connected() is False
#     await madvr_instance.open_connection()  # Reopen for the next tests


@pytest.mark.asyncio(scope="session")
async def test_process_info(madvr_instance):
    print("Testing process info")
    """Verify the process info func works to assign attrs, with modifications"""
    await madvr_instance._process_notifications(
        'Welcome\r\nOk\r\nIncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9\r\nAspectRatio 129x123 1.78 178 "TV"\r\nOutgoingSignalInfo 3840x2160 23.976p 2D 444 12bit HDR10 2020 TV\r\n'
    )
    await madvr_instance._process_notifications(
        "IncomingSignalInfo 4096x2160 60p 2D 444 12bit HDR10 2020 TV 16:9\r\n"
    )
    assert madvr_instance.msg_dict == {
        "incoming_res": "4096x2160",
        "incoming_frame_rate": "60p",
        "incoming_color_space": "444",
        "incoming_bit_depth": "12bit",
        "is_signal": True,
        "hdr_flag": True,
        "incoming_colorimetry": "2020",
        "incoming_black_levels": "TV",
        "incoming_aspect_ratio": "16:9",
        "aspect_res": "129x123",
        "aspect_dec": 1.78,
        "aspect_int": "178",
        "aspect_name": '"TV"',
        "outgoing_res": "3840x2160",
        "outgoing_frame_rate": "23.976p",
        "outgoing_color_space": "444",
        "outgoing_bit_depth": "12bit",
        "outgoing_hdr_flag": True,
        "outgoing_colorimetry": "2020",
        "outgoing_black_levels": "TV",
    }


@pytest.mark.asyncio(scope="session")
async def test_send_command(madvr_instance):
    print("Testing send command")
    """Verify the send command func works"""
    try:
        await asyncio.wait_for(madvr_instance.read_notifications(), timeout=5)
    except asyncio.TimeoutError:
        pass
    result = await madvr_instance.send_command(["GetIncomingSignalInfo"])
    assert result == "ok"
