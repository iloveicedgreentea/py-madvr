"""Simple integration test - no fixtures, no bullshit."""

import asyncio
import os
import socket
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from pymadvr.madvr import Madvr


def is_device_available():
    """Check if MadVR device is reachable."""
    host = os.getenv("MADVR_HOST", "192.168.1.100")
    port = int(os.getenv("MADVR_PORT", "44077"))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# Skip all tests in this module if device is not available
pytestmark = pytest.mark.skipif(
    not is_device_available(),
    reason="MadVR device not available at MADVR_HOST:MADVR_PORT"
)


@pytest.mark.asyncio
async def test_basic_connection():
    """Test basic connection and data retrieval."""
    host = os.getenv("MADVR_HOST", "192.168.1.100")
    port = int(os.getenv("MADVR_PORT", "44077"))

    # Create instance
    madvr = Madvr(host, port=port)

    try:
        # Connect
        await madvr.open_connection()

        # Wait a bit for data
        await asyncio.sleep(2)

        # Check basic properties
        assert madvr.connected is True
        assert isinstance(madvr.is_on, bool)

        # Check msg_dict
        assert "is_on" in madvr.msg_dict
        assert madvr.msg_dict["is_on"] is True

        # If MAC is available, check it
        if madvr.mac_address:
            assert len(madvr.mac_address) > 0
            assert ":" in madvr.mac_address or "-" in madvr.mac_address

        # Send a command
        response = await madvr.send_command(["GetMacAddress"])
        assert response is not None

        # Test menu commands
        await madvr.add_command_to_queue(["OpenMenu", "Info"])
        await asyncio.sleep(1)
        await madvr.add_command_to_queue(["CloseMenu"])
        await asyncio.sleep(1)

        print(f"✓ Test passed! Device info: {madvr.msg_dict}")

    finally:
        await madvr.close_connection()


@pytest.mark.asyncio
async def test_display_message():
    """Test display message functionality."""
    host = os.getenv("MADVR_HOST", "192.168.1.100")
    port = int(os.getenv("MADVR_PORT", "44077"))

    madvr = Madvr(host, port=port)

    try:
        await madvr.open_connection()
        await asyncio.sleep(1)

        # Send display message
        await madvr.display_message(3, "Hello from Python!")
        await asyncio.sleep(4)

        print("✓ Display message test passed!")

    finally:
        await madvr.close_connection()


@pytest.mark.asyncio
async def test_ha_command_formats():
    """Test Home Assistant command formats that were failing."""
    host = os.getenv("MADVR_HOST", "192.168.1.100")
    port = int(os.getenv("MADVR_PORT", "44077"))

    madvr = Madvr(host, port=port)

    try:
        await madvr.open_connection()
        await asyncio.sleep(1)

        # Test the exact commands that were failing in HA logs
        print("Testing HA command formats...")

        # Test KeyPress commands (comma-separated format from HA)
        await madvr.add_command_to_queue(["KeyPress, MENU"])
        await asyncio.sleep(2)

        await madvr.add_command_to_queue(["KeyPress, MENU"])  # Close menu
        await asyncio.sleep(1)

        # Test OpenMenu command
        await madvr.add_command_to_queue(["OpenMenu, Info"])
        await asyncio.sleep(2)

        await madvr.add_command_to_queue(["CloseMenu"])
        await asyncio.sleep(1)

        print("✓ HA command format test passed!")

    finally:
        await madvr.close_connection()


if __name__ == "__main__":
    # Run directly without pytest
    async def main():
        print(f"Testing MadVR at {os.getenv('MADVR_HOST', '192.168.1.100')}")

        try:
            await test_basic_connection()
            await test_display_message()
            await test_ha_command_formats()
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()

    asyncio.run(main())
