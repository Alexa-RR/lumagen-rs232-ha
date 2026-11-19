"""Client tests against the in-memory device."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.lumagen.pylumagen import (
    LumagenClient,
    LumagenConnectionError,
    LumagenTimeoutError,
    Message,
    async_probe,
)

from .fake_lumagen import I24_NO_SOURCE, FakeLumagen


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0)


async def test_refresh_reads_everything(fake_lumagen: FakeLumagen) -> None:
    client = LumagenClient("/dev/ttyUSB0", query_timeout=0.2)
    await client.connect()
    try:
        state = await client.refresh()
        assert fake_lumagen.connect_calls == [("/dev/ttyUSB0", {"baudrate": 9600})]
        assert state.identity is not None
        assert state.identity.serial_number == "1234"
        assert state.power is True
        assert state.current_input == 3
        assert state.current_memory == "A"
        assert state.game_mode is False
        assert state.full_info is not None
        assert state.full_info.is_hdr is True
        # No stray <CR> after queries (it would pop up the Info page).
        assert "\r" not in fake_lumagen.received
    finally:
        await client.close()


async def test_falls_back_to_older_full_info_query(fake_lumagen: FakeLumagen) -> None:
    fake_lumagen.silent = {"ZQI25", "ZQI24", "ZQI23"}
    fake_lumagen.full_info = "I22,1,059,1080,0,1,178,178,-,0,0003,0,0,060,2160,178,1,0,p,P"

    def answer_i22(query: str, original=fake_lumagen._answer) -> None:
        if query == "ZQI22":
            fake_lumagen._send(f"!{fake_lumagen.full_info}\r\n")
        else:
            original(query)

    fake_lumagen._answer = answer_i22  # type: ignore[method-assign]
    client = LumagenClient("/dev/ttyUSB0", query_timeout=0.05)
    await client.connect()
    try:
        await client.refresh()
        assert client.state.full_info is not None
        assert client.state.full_info.source_frame_rate == 59.94
        # The working query is remembered, so the next refresh skips I25-I23.
        fake_lumagen.received = ""
        await client.refresh()
        assert "ZQI25" not in fake_lumagen.received
        assert "ZQI24" not in fake_lumagen.received
        assert "ZQI22" in fake_lumagen.received
    finally:
        await client.close()


async def test_standby_only_polls_power(fake_lumagen: FakeLumagen) -> None:
    fake_lumagen.power = False
    client = LumagenClient("/dev/ttyUSB0", query_timeout=0.05)
    await client.connect()
    try:
        state = await client.refresh()
        assert state.power is False
        assert "ZQI" not in fake_lumagen.received
    finally:
        await client.close()


async def test_query_timeout(fake_lumagen: FakeLumagen) -> None:
    fake_lumagen.silent = {"ZQS02"}
    client = LumagenClient("/dev/ttyUSB0", query_timeout=0.05)
    await client.connect()
    try:
        with pytest.raises(LumagenTimeoutError):
            await client.refresh()
    finally:
        await client.close()


async def test_unsolicited_reports_reach_listeners(fake_lumagen: FakeLumagen) -> None:
    client = LumagenClient("/dev/ttyUSB0")
    received: list[Message] = []
    client.add_message_listener(received.append)
    await client.connect()
    try:
        fake_lumagen.push(I24_NO_SOURCE)
        await _wait_for(lambda: received)
        assert received[0].code == "I24"
        assert client.state.full_info is not None
        assert client.state.full_info.has_source is False
        # Replies to our own queries are not reported as unsolicited.
        received.clear()
        await client.query("ZQS02")
        assert received == []
    finally:
        await client.close()


async def test_commands_send_exact_bytes(fake_lumagen: FakeLumagen) -> None:
    client = LumagenClient("/dev/ttyUSB0")
    await client.connect()
    try:
        await client.standby()
        await client.power_on()
        await client.select_input(12)
        await client.select_memory("B")
        await client.set_game_mode(True)
        await client.send_key("aspect_2_40")
        assert fake_lumagen.received == "$%i+2bZY5511\rG"
        assert (fake_lumagen.input, fake_lumagen.memory, fake_lumagen.game_mode) == (
            12,
            "B",
            True,
        )
        with pytest.raises(ValueError):
            await client.send_key("nope")
    finally:
        await client.close()


async def test_reconnects_after_drop(fake_lumagen: FakeLumagen) -> None:
    client = LumagenClient("socket://pi.local:2000")
    events: list[bool] = []
    client.add_connection_listener(events.append)
    await client.connect()
    try:
        fake_lumagen.drop_connection()
        await _wait_for(lambda: events == [True, False, True])
        assert len(fake_lumagen.connect_calls) == 2
        assert (await client.query("ZQS02")).data == "1"
    finally:
        await client.close()
    assert client.connected is False


async def test_pending_query_fails_when_connection_drops(fake_lumagen: FakeLumagen) -> None:
    fake_lumagen.silent = {"ZQS02"}
    client = LumagenClient("/dev/ttyUSB0", reconnect=False)
    await client.connect()
    try:
        task = asyncio.create_task(client.query("ZQS02", timeout=5))
        await asyncio.sleep(0.01)
        fake_lumagen.drop_connection()
        with pytest.raises(LumagenConnectionError):
            await task
        with pytest.raises(LumagenConnectionError):
            await client.power_on()
    finally:
        await client.close()


async def test_probe(fake_lumagen: FakeLumagen) -> None:
    identity = await async_probe("rfc2217://pi.local:2000")
    assert identity.model_name == "RadiancePro"
    fake_lumagen.refuse_connections = True
    with pytest.raises(LumagenConnectionError):
        await async_probe("/dev/missing")
