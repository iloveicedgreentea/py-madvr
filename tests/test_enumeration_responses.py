"""Enumeration replies must be complete despite TCP fragmentation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymadvr.madvr import Madvr


def direct_connection(monkeypatch, fragments, *, eof=False):
    """Deliver response bytes only after the command is written."""
    reader = asyncio.StreamReader()
    reader.feed_data(b"WELCOME\r\n")
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    feeders = []

    async def feed_response():
        for fragment in fragments:
            reader.feed_data(fragment)
            await asyncio.sleep(0)
        if eof:
            reader.feed_eof()

    writer.write.side_effect = lambda _: feeders.append(asyncio.create_task(feed_response()))
    opened = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr("pymadvr.madvr.asyncio.open_connection", opened)
    return writer, opened, feeders


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "record"),
    [
        (["EnumProfileGroups"], "ProfileGroup"),
        (["EnumProfiles", "SOURCE"], "Profile"),
        (["EnumSettingPages"], "SettingPage"),
        (["EnumConfigPages"], "ConfigPage"),
        (["EnumOptions", r"temporary\hdrSettings"], "Option"),
    ],
)
@pytest.mark.parametrize("separator", [b"\r", b"\n", b"\r\n"])
async def test_fragmented_enumeration_uses_own_connection(monkeypatch, command, record, separator):
    """Large replies survive split delimiters and cannot enter the command pool."""
    records = [f'{record} item{index} "' + "é" * 50 + '"' for index in range(30)]
    payload = (
        separator.join(
            [b"OK", b"AspectRatio 2.40", *(line.encode() for line in records), f"{record}.".encode(), b"TRAILING"]
        )
        + separator
    )
    assert len(payload) > 1024
    fragments = [payload[index : index + 7] for index in range(0, len(payload), 7)]
    writer, opened, feeders = direct_connection(monkeypatch, fragments)
    client = Madvr("192.0.2.1")
    client.connection_pool.send_command = AsyncMock(return_value="MacAddress 001122334455")

    response = await client.send_command(command)
    await asyncio.gather(*feeders)

    assert response is not None
    assert all(line in response for line in records)
    assert "TRAILING" not in response
    assert "AspectRatio" not in response
    opened.assert_awaited_once()
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()
    client.connection_pool.send_command.assert_not_awaited()

    assert await client.send_command(["GetMacAddress"]) == "MacAddress 001122334455"
    client.connection_pool.send_command.assert_awaited_once_with(b"GetMacAddress\r\n")


@pytest.mark.asyncio
async def test_enumeration_error_closes_direct_connection(monkeypatch):
    """An explicit device error ends the response without waiting for a terminator."""
    writer, _, feeders = direct_connection(monkeypatch, [b"ERR", b"OR invalid group\r", b"\n"])
    response = await Madvr("192.0.2.1").send_command(["EnumProfiles", "unknown"])
    await asyncio.gather(*feeders)
    assert response == "ERROR invalid group"
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_fragmented_welcome_preserves_early_enumeration_record(monkeypatch):
    """Reading a split greeting must leave coalesced response bytes intact."""
    reader = asyncio.StreamReader()
    reader.feed_data(b"WEL")
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    writer.write.side_effect = lambda _: reader.feed_data(b"ProfileGroup.\r\n")

    async def finish_welcome():
        await asyncio.sleep(0)
        reader.feed_data(b"COME\r\nProfileGroup EARLY\r\n")

    feeder = asyncio.create_task(finish_welcome())
    monkeypatch.setattr("pymadvr.madvr.asyncio.open_connection", AsyncMock(return_value=(reader, writer)))
    response = await Madvr("192.0.2.1").send_command(["EnumProfileGroups"])
    await feeder
    assert response == "ProfileGroup EARLY\nProfileGroup."
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_enumeration_eof_before_terminator_fails(monkeypatch):
    """An interrupted list must never be returned as a successful partial list."""
    writer, _, feeders = direct_connection(monkeypatch, [b"ProfileGroup SOURCE\r\n"], eof=True)
    with pytest.raises(ConnectionError):
        await Madvr("192.0.2.1").send_command(["EnumProfileGroups"])
    await asyncio.gather(*feeders)
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_enumeration_timeout_closes_direct_connection(monkeypatch):
    """A device that never finishes listing remains bounded by the response timeout."""
    writer, _, feeders = direct_connection(monkeypatch, [b"ProfileGroup SOURCE\r\n"])
    monkeypatch.setattr("pymadvr.madvr.COMMAND_RESPONSE_TIMEOUT", 0.01)
    with pytest.raises(ConnectionError):
        await Madvr("192.0.2.1").send_command(["EnumProfileGroups"])
    await asyncio.gather(*feeders)
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()
