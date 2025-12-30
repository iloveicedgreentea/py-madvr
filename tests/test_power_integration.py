"""Integration tests for power on/off functionality.

These tests require a real MadVR device and will actually turn it on/off!
Set environment variables:
  - MADVR_HOST: Device IP address (default: 192.168.1.100)
  - MADVR_PORT: Device port (default: 44077)
  - MADVR_MAC: Device MAC address (required for power on test)

Tests:
  - test_power_on_from_off: Tests WOL power on (only runs if device is off)
  - test_power_cycle: Single test that covers power_off, standby, ping detection,
    and connection cleanup - all in one power cycle to avoid skip issues
"""

import asyncio
import os
import socket
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from pymadvr.madvr import Madvr
from pymadvr.wol import send_magic_packet


# Timeouts for waiting on device state changes
WAIT_TIMEOUT = 300.0  # Max seconds to wait for device state change
POLL_INTERVAL = 0.5  # Seconds between polls


def get_test_config() -> tuple[str, int, str]:
    """Get test configuration from environment variables."""
    host = os.getenv("MADVR_HOST", "192.168.1.100")
    port = int(os.getenv("MADVR_PORT", "44077"))
    mac = os.getenv("MADVR_MAC", "")
    return host, port, mac


def is_device_pingable(host: str, port: int) -> bool:
    """Check if device is reachable via TCP connection."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


async def wait_until_device_off(host: str, port: int, timeout: float = WAIT_TIMEOUT) -> bool:
    """Wait until device is no longer pingable. Returns True if device went offline."""
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        if not is_device_pingable(host, port):
            return True
        await asyncio.sleep(POLL_INTERVAL)
    return False


async def wait_until_device_on(host: str, port: int, timeout: float = WAIT_TIMEOUT) -> bool:
    """Wait until device is pingable. Returns True if device came online."""
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        if is_device_pingable(host, port):
            return True
        await asyncio.sleep(POLL_INTERVAL)
    return False


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to colon-separated format."""
    # Remove all common separators and convert to uppercase
    mac_clean = mac.upper().replace("-", "").replace(":", "").replace(".", "")
    if len(mac_clean) != 12:
        return mac  # Return as-is if we can't parse it
    # Format as colon-separated
    return ":".join(mac_clean[i:i+2] for i in range(0, 12, 2))


async def power_on_and_wait(mac: str | None, host: str, port: int, timeout: float = WAIT_TIMEOUT) -> bool:
    """Power on device via WOL and wait until it's pingable. Returns True if successful.

    Sends multiple WOL packets to improve reliability, as the device may not be
    ready to receive WOL immediately after power off.
    """
    if not mac:
        print("No MAC address available, cannot power on device")
        return False

    # Normalize MAC address (device returns dash-separated, but let's be consistent)
    mac_normalized = normalize_mac(mac)
    print(f"Powering device on via WOL (MAC: {mac_normalized})...")

    # Send initial WOL packet
    send_magic_packet(mac_normalized)

    print(f"Waiting up to {timeout}s for device to come online...")
    start = asyncio.get_event_loop().time()
    wol_retry_interval = 5.0  # Send WOL every 5 seconds if device not online yet
    last_wol_time = start

    while asyncio.get_event_loop().time() - start < timeout:
        if is_device_pingable(host, port):
            print("Device is online!")
            return True

        # Send another WOL packet every few seconds
        current_time = asyncio.get_event_loop().time()
        if current_time - last_wol_time >= wol_retry_interval:
            print("  Retrying WOL packet...")
            send_magic_packet(mac_normalized)
            last_wol_time = current_time

        await asyncio.sleep(POLL_INTERVAL)

    print("WARNING: Device did not come online within timeout")
    return False


async def get_mac_address(madvr: Madvr, timeout: float = 10.0) -> str:
    """Get MAC address from device, waiting if necessary."""
    # First check if we already have it
    if madvr.mac_address:
        return madvr.mac_address

    # Try to fetch it explicitly
    try:
        await madvr.send_command(["GetMacAddress"])
    except Exception:
        pass

    # Wait for it to appear in msg_dict
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        if madvr.mac_address:
            return madvr.mac_address
        await asyncio.sleep(POLL_INTERVAL)

    return ""


@pytest.mark.asyncio
async def test_power_on_from_off():
    """
    Integration test: Verify power_on() works when device is OFF.

    This test only runs if the device is currently off. It:
    1. Sends WOL packet
    2. Waits until device is pingable
    3. Connects and verifies is_on is True
    4. Verifies HA callback was called with is_on=True

    Requires MADVR_MAC environment variable to be set.
    """
    host, port, mac = get_test_config()

    # Only run if device is off
    if is_device_pingable(host, port):
        pytest.skip("Device is already on - cannot test power on from off state")

    # Need MAC address to power on
    if not mac:
        pytest.skip("MADVR_MAC environment variable required for power on test")

    print(f"Device is OFF, will power on using MAC: {mac}")

    madvr = Madvr(host, port=port, mac=mac)

    # Track HA updates
    ha_updates: list[dict] = []
    def track_update(data):
        ha_updates.append(data.copy())
    madvr.set_update_callback(track_update)

    try:
        # Power on the device
        print("Sending WOL packet...")
        await madvr.power_on(mac=mac)

        # Wait until device is pingable
        print("Waiting for device to come online...")
        came_online = await wait_until_device_on(host, port)
        assert came_online, "Device did not come online within timeout"

        # Now connect to the device
        print("Connecting to device...")
        await madvr.open_connection()

        # Verify state
        assert madvr.is_on is True, "is_on should be True after power_on"
        assert madvr.msg_dict.get("is_on") is True, "msg_dict['is_on'] should be True"

        # Verify standby flag is cleared
        assert madvr.is_standby is False, "is_standby should be False after power_on"
        assert madvr.msg_dict.get("standby") is False, "msg_dict['standby'] should be False"

        # Verify HA was notified with is_on=True
        found_on_update = any(update.get("is_on") is True for update in ha_updates)
        assert found_on_update, f"HA should have received is_on=True update. Updates: {ha_updates}"

        print("power_on test passed!")
        print(f"  - is_on: {madvr.is_on}")
        print(f"  - is_standby: {madvr.is_standby}")
        print(f"  - HA updates: {len(ha_updates)}")

    finally:
        await madvr.close_connection()


@pytest.mark.asyncio
async def test_power_cycle():
    """
    Integration test: Complete power cycle test using a single client.

    This test performs all power-related checks in a single test to avoid
    issues with device being off between separate tests. It covers:

    1. Power off (regular) - verifies state update and HA callback
    2. Connection cleanup - verifies notification connection is cleared
    3. Ping detection - verifies ping task correctly detects offline state
    4. Power on via WOL - restores device
    5. Standby mode - verifies standby flag is set correctly
    6. Power on via WOL - final restore

    WARNING: This test will turn off your MadVR device multiple times!
    """
    host, port, mac_env = get_test_config()

    # Skip if device is not available
    if not is_device_pingable(host, port):
        pytest.skip("Device is not available (offline)")

    madvr = Madvr(host, port=port)
    mac = mac_env  # May be overwritten by device MAC

    # Track HA updates
    ha_updates: list[dict] = []
    def track_update(data):
        ha_updates.append(data.copy())
    madvr.set_update_callback(track_update)

    try:
        # ================================================================
        # SETUP: Connect and get MAC address
        # ================================================================
        print("=" * 60)
        print("SETUP: Connecting to device...")
        print("=" * 60)

        await madvr.open_connection()

        assert madvr.is_on is True, "Device must be ON for this test"
        assert madvr.msg_dict.get("is_on") is True
        assert madvr.notification_connected.is_set(), "Notification should be connected"

        # Get MAC address from device if not provided via env
        device_mac = await get_mac_address(madvr)
        if device_mac:
            mac = device_mac
        assert mac, "MAC address required (set MADVR_MAC or device must provide it)"

        print(f"Device is ON, MAC: {mac}")
        print(f"Initial msg_dict: {madvr.msg_dict}")

        # ================================================================
        # TEST 1: Power off (regular)
        # ================================================================
        print()
        print("=" * 60)
        print("TEST 1: Power off (regular)")
        print("=" * 60)

        ha_updates.clear()

        print("Sending PowerOff command...")
        await madvr.power_off()

        # Verify immediate state change
        assert madvr.is_on is False, "is_on should be False immediately after power_off"
        assert madvr.msg_dict.get("is_on") is False, "msg_dict['is_on'] should be False"
        assert madvr.is_standby is False, "is_standby should be False for regular power off"

        # Verify notification connection was cleared immediately
        assert not madvr.notification_connected.is_set(), "Notification connection should be cleared"
        assert madvr.notification_reader is None, "notification_reader should be None"
        assert madvr.notification_writer is None, "notification_writer should be None"

        # Verify HA was notified
        assert len(ha_updates) >= 1, "HA callback should have been called"
        found_off_update = any(update.get("is_on") is False for update in ha_updates)
        assert found_off_update, f"HA should have received is_on=False update. Updates: {ha_updates}"

        # Wait until device is actually off (not pingable)
        print("Waiting for device to go offline...")
        went_offline = await wait_until_device_off(host, port)
        assert went_offline, "Device did not go offline within timeout"

        # Verify state remains off (ping task should not revert it)
        assert madvr.is_on is False, "State should remain False after device offline"

        # Verify device is actually not connectable
        is_connectable = await madvr.is_device_connectable()
        assert is_connectable is False, "Device should not be connectable after power off"

        print("TEST 1 PASSED: Power off works correctly")
        print(f"  - is_on: {madvr.is_on}")
        print(f"  - notification_connected: {madvr.notification_connected.is_set()}")
        print(f"  - HA updates received: {len(ha_updates)}")

        # ================================================================
        # RESTORE: Power on for next test
        # ================================================================
        print()
        print("=" * 60)
        print("RESTORE: Powering device back on...")

        # Give device a moment to fully shut down before WOL
        print("Waiting 5s for device to fully shut down...")
        await asyncio.sleep(5.0)
        print("=" * 60)

        came_online = await power_on_and_wait(mac, host, port)
        assert came_online, "Device did not come back online"

        # Reconnect
        print("Reconnecting...")
        await madvr.open_connection()
        assert madvr.is_on is True, "Device should be on after reconnect"

        # ================================================================
        # TEST 2: Standby mode
        # ================================================================
        print()
        print("=" * 60)
        print("TEST 2: Standby mode")
        print("=" * 60)

        ha_updates.clear()

        print("Sending Standby command...")
        await madvr.power_off(standby=True)

        # Verify state
        assert madvr.is_on is False, "is_on should be False after standby"
        assert madvr.is_standby is True, "is_standby should be True"
        assert madvr.msg_dict.get("standby") is True, "msg_dict['standby'] should be True"

        # Verify HA update includes standby
        found_standby_update = any(
            update.get("is_on") is False and update.get("standby") is True
            for update in ha_updates
        )
        assert found_standby_update, f"HA should have received standby=True update. Updates: {ha_updates}"

        # Wait for device to go offline
        print("Waiting for device to go offline...")
        went_offline = await wait_until_device_off(host, port)
        assert went_offline, "Device did not go offline within timeout"

        print("TEST 2 PASSED: Standby mode works correctly")
        print(f"  - is_on: {madvr.is_on}")
        print(f"  - is_standby: {madvr.is_standby}")
        print(f"  - msg_dict standby: {madvr.msg_dict.get('standby')}")

        # ================================================================
        # FINAL RESTORE: Power on
        # ================================================================
        print()
        print("=" * 60)
        print("FINAL RESTORE: Powering device back on...")
        print("=" * 60)

        # Give device a moment to fully shut down before WOL
        print("Waiting 5s for device to fully shut down...")
        await asyncio.sleep(5.0)

        came_online = await power_on_and_wait(mac, host, port)
        assert came_online, "Device did not come back online for final restore"

        print()
        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)

    finally:
        await madvr.close_connection()
        # Ensure device is on when we're done
        if not is_device_pingable(host, port):
            print("Final cleanup: Waiting 5s then powering device on...")
            await asyncio.sleep(5.0)
            await power_on_and_wait(mac, host, port)


if __name__ == "__main__":
    # Run directly without pytest
    async def main():
        host, port, mac = get_test_config()

        print(f"Testing MadVR power functions at {host}:{port}")
        if mac:
            print(f"MAC address: {mac}")
        print("WARNING: These tests will turn on/off your MadVR device!")
        print()

        try:
            await test_power_on_from_off()
        except Exception as e:
            if "skip" in str(e).lower():
                print(f"Skipped: {e}")
            else:
                raise

        try:
            await test_power_cycle()
            print("\nAll power tests passed!")
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(main())
