"""An in-memory stand-in for a Radiance Pro on the end of a serial cable."""

from __future__ import annotations

import asyncio
from typing import Any

# A 4K23.98 HDR source on input 3, 2.40 content, 4K output.
I24_4K_HDR = "I24,1,023,2160,0,0,178,240,-,0,0001,1,2,023,2160,178,3,1,p,P,3,2,178,240"
I24_NO_SOURCE = "I24,0,000,0000,0,0,000,000,-,0,0001,0,0,060,2160,178,1,0,-,P,1,1,000,000"


class FakeWriter:
    """Minimal asyncio.StreamWriter replacement that feeds the fake device."""

    def __init__(self, device: FakeLumagen) -> None:
        self._device = device
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.closed:
            raise OSError("write to closed port")
        self._device.receive(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeLumagen:
    """Answers queries, echoes input and tracks state like the real unit."""

    def __init__(self) -> None:
        self.echo = True
        self.power = True
        self.input = 3
        self.memory = "A"
        self.game_mode = False
        self.full_info = I24_4K_HDR
        self.identity = "S01,RadiancePro,060124,4242,1234"
        self.labels = {("A", 1): "Apple TV", ("A", 3): "Kaleidescape"}
        self.silent: set[str] = set()
        """Queries the fake ignores (to simulate older firmware or standby)."""
        self.refuse_connections = False

        self.received = ""
        self.connect_calls: list[tuple[str, dict[str, Any]]] = []
        self._buffer = ""
        self._reader: asyncio.StreamReader | None = None
        self._writer: FakeWriter | None = None

    # ---- Hooked in place of serialx.open_serial_connection ---------------

    async def open_serial_connection(
        self, url: str, **kwargs: Any
    ) -> tuple[asyncio.StreamReader, FakeWriter]:
        self.connect_calls.append((url, kwargs))
        if self.refuse_connections:
            raise OSError("No such file or directory")
        self._reader = asyncio.StreamReader()
        self._writer = FakeWriter(self)
        self._buffer = ""
        return self._reader, self._writer

    # ---- Test controls ---------------------------------------------------

    def push(self, payload: str) -> None:
        """Send an unsolicited report, e.g. ``I24,...``."""
        self._send(f"!{payload}\r\n")

    def drop_connection(self) -> None:
        """Simulate the cable being pulled / the bridge going away."""
        assert self._reader is not None
        self._reader.feed_eof()

    # ---- Device behaviour -------------------------------------------------

    def _send(self, text: str) -> None:
        if self._reader is not None and not self._reader.at_eof():
            self._reader.feed_data(text.encode("ascii"))

    def receive(self, data: bytes) -> None:
        text = data.decode("ascii")
        self.received += text
        if self.echo:
            self._send(text)
        self._buffer += text
        self._process()

    def _process(self) -> None:
        while self._buffer:
            buf = self._buffer
            if buf.startswith("ZQS1"):
                if len(buf) < 6:
                    return
                self._answer_label(buf[4], int(buf[5]) + 1)
                self._buffer = buf[6:]
            elif buf.startswith("ZQ"):
                if len(buf) < 5:
                    return
                self._answer(buf[:5])
                self._buffer = buf[5:]
            elif buf[0] == "Z":
                if "\r" not in buf:
                    return
                command, _, self._buffer = buf.partition("\r")
                if command.startswith("ZY551"):
                    self.game_mode = command[5:] == "1"
                elif command.startswith("ZY524"):
                    target, number, label = command[5], int(command[6]) + 1, command[7:]
                    for memory in "ABCD" if target == "0" else target:
                        self.labels[(memory, number)] = label
            elif buf[0] == "i":
                if len(buf) < 2 or (buf[1] == "+" and len(buf) < 3):
                    return
                if buf[1] == "+":
                    self.input, self._buffer = 10 + int(buf[2]), buf[3:]
                else:
                    self.input, self._buffer = int(buf[1]), buf[2:]
            else:
                char, self._buffer = buf[0], buf[1:]
                if char == "%":
                    self.power = True
                elif char == "$":
                    self.power = False
                elif char in "abcd":
                    self.memory = char.upper()

    def _answer(self, query: str) -> None:
        if query in self.silent:
            return
        reply = {
            "ZQS00": "S00,Ok",
            "ZQS01": self.identity,
            "ZQS02": f"S02,{int(self.power)}",
        }.get(query)
        if reply is None and self.power:
            reply = {
                "ZQI00": f"I00,{self.input},{self.memory},{self.input}",
                "ZQI53": f"I53,{int(self.game_mode)}",
                "ZQI24": self.full_info,
                "ZQI25": self._full_info_v5(),
            }.get(query)
        if reply is not None:
            self._send(f"!{reply}\r\n")

    def _full_info_v5(self) -> str | None:
        """ZQI25 = the ZQI24 fields plus memory, unknown, sub shift, auto aspect."""
        if not self.full_info.startswith("I24,"):
            return None
        return f"I25,{self.full_info[4:]},{self.memory},0,0,2"

    def _answer_label(self, memory: str, number: int) -> None:
        label = self.labels.get((memory, number), f"Input {number}{memory}")
        self._send(f"!S1{memory},{label}\r\n")
