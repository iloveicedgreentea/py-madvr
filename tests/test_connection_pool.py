"""Test the connection pool timeout behavior."""

import asyncio
import os

import pytest

from pymadvr.madvr import Madvr


@pytest.fixture
def madvr_config():
    """Fixture providing MadVR connection configuration."""
    return {"host": os.getenv("MADVR_HOST", "192.168.1.100"), "port": int(os.getenv("MADVR_PORT", "44077"))}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_connection_pool_timeout(madvr_config):
    """Test connection pool timeout behavior."""
    madvr = Madvr(madvr_config["host"], port=madvr_config["port"])

    # Check if device is available
    if not await madvr.is_device_connectable():
        pytest.skip(f"MadVR device not available at {madvr_config['host']}:{madvr_config['port']}")

    try:
        await madvr.open_connection()

        # Send first command - should create pooled connection
        response1 = await madvr.send_command(["GetMacAddress"])
        assert response1 is not None

        # Send second command quickly - should reuse connection
        response2 = await madvr.send_command(["GetTemperatures"])
        assert response2 is not None

        # Wait 5 seconds - connection should still be alive
        await asyncio.sleep(5)

        # Send third command - should reuse connection, reset timer
        response3 = await madvr.send_command(["GetMacAddress"])
        assert response3 is not None

        # Wait 12 seconds - connection should timeout and close
        await asyncio.sleep(12)

        # Send fourth command - should create new connection
        response4 = await madvr.send_command(["GetMacAddress"])
        assert response4 is not None

    finally:
        # Properly close connection and cancel all tasks
        await madvr.close_connection()

        # Cancel the immortal tasks that don't get cancelled by close_connection
        if madvr.ping_task and not madvr.ping_task.done():
            madvr.ping_task.cancel()
            try:
                await madvr.ping_task
            except asyncio.CancelledError:
                pass

        if madvr.refresh_task and not madvr.refresh_task.done():
            madvr.refresh_task.cancel()
            try:
                await madvr.refresh_task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_connection_reuse(madvr_config):
    """Test that multiple rapid commands reuse the same connection."""
    madvr = Madvr(madvr_config["host"], port=madvr_config["port"])

    # Check if device is available
    if not await madvr.is_device_connectable():
        pytest.skip(f"MadVR device not available at {madvr_config['host']}:{madvr_config['port']}")

    try:
        await madvr.open_connection()

        # Send multiple commands rapidly
        responses = []
        for i in range(5):
            response = await madvr.send_command(["GetMacAddress"])
            responses.append(response)
            assert response is not None

        # All commands should succeed
        assert len(responses) == 5
        assert all(r is not None for r in responses)

    finally:
        await madvr.close_connection()
        # Cancel immortal tasks
        for task in [madvr.ping_task, madvr.refresh_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_background_tasks_dont_interfere(madvr_config):
    """Test that background tasks don't interfere with user commands."""
    madvr = Madvr(madvr_config["host"], port=madvr_config["port"])

    # Check if device is available
    if not await madvr.is_device_connectable():
        pytest.skip(f"MadVR device not available at {madvr_config['host']}:{madvr_config['port']}")

    try:
        await madvr.open_connection()

        # Wait a bit for background tasks to start
        await asyncio.sleep(2)

        # Send user command - should work despite background tasks
        response = await madvr.send_command(["GetMacAddress"])
        assert response is not None

        # Send another command after a delay
        await asyncio.sleep(3)
        response2 = await madvr.send_command(["GetTemperatures"])
        assert response2 is not None

    finally:
        await madvr.close_connection()
        # Cancel immortal tasks
        for task in [madvr.ping_task, madvr.refresh_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


if __name__ == "__main__":
    # Run tests directly
    async def main():
        print("Running connection pool tests...")

        try:
            await test_connection_pool_timeout()
            print("✓ Connection pool timeout test passed")

            await test_connection_reuse()
            print("✓ Connection reuse test passed")

            await test_background_tasks_dont_interfere()
            print("✓ Background task interference test passed")

            print("\n✓ All tests passed!")

        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()

    asyncio.run(main())
