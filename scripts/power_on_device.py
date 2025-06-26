#!/usr/bin/env python3
"""Script to power on MadVR device using Wake-on-LAN for testing."""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import madvr module
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymadvr.madvr import Madvr
from pymadvr.wol import send_magic_packet


async def power_on_device(host: str, port: int, timeout: int = 60) -> bool:
    """
    Power on MadVR device using Wake-on-LAN.

    Args:
        host: Device IP address
        port: Device port
        timeout: Maximum time to wait for device to come online

    Returns:
        True if device is powered on successfully
    """
    logger = logging.getLogger(__name__)
    madvr = Madvr(
        host=host,
        port=port,
        logger=logger,
        connect_timeout=10,
    )

    # Check if device is already on
    if await madvr.is_device_connectable():
        logger.info(f"Device at {host}:{port} is already on")
        return True

    # MAC address must come from environment variable
    mac = os.getenv("MADVR_MAC", "")
    if not mac:
        logger.error("MADVR_MAC environment variable not set. Cannot power on device without MAC address.")
        return False

    logger.info(f"Sending Wake-on-LAN packet to MAC {mac}")

    try:
        send_magic_packet(mac, logger=logger)
    except Exception as e:
        logger.error(f"Failed to send WOL packet: {e}")
        return False

    # Wait for device to come online
    logger.info(f"Waiting up to {timeout} seconds for device to come online...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if await madvr.is_device_connectable():
            logger.info(f"Device is now online! (took {int(time.time() - start_time)} seconds)")

            # Give device a moment to fully initialize
            await asyncio.sleep(3.0)
            return True

        await asyncio.sleep(2.0)
        sys.stdout.write(".")
        sys.stdout.flush()

    logger.error(f"Device did not come online after {timeout} seconds")
    return False


async def main():
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Get configuration from environment
    host = os.getenv("MADVR_HOST", "192.168.1.100")
    port = int(os.getenv("MADVR_PORT", "44077"))

    # Try to power on device
    success = await power_on_device(host, port)

    if success:
        print(f"\n✓ Device at {host}:{port} is powered on and ready")
        print("\nYou can now run integration tests:")
        print("  pytest tests/test_integration.py -m integration -v")
        sys.exit(0)
    else:
        print(f"\n✗ Failed to power on device at {host}:{port}")
        print("\nMake sure MADVR_MAC environment variable is set correctly")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
