"""Async client for a Lumagen Radiance processor over serialx."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

import serialx

from . import commands
from .exceptions import LumagenConnectionError, LumagenError, LumagenTimeoutError
from .models import Identity, LumagenState
from .protocol import LineSplitter, Message, parse_line, query_code

_LOGGER = logging.getLogger(__name__)

BAUDRATE = 9600
CONNECT_TIMEOUT = 10.0
QUERY_TIMEOUT = 2.0
RECONNECT_DELAYS = (1, 2, 5, 10, 30)

_SERIAL_ERRORS = (OSError, serialx.SerialException)

type MessageListener = Callable[[Message], None]
type ConnectionListener = Callable[[bool], None]


class LumagenClient:
    """Keeps one connection to the processor open and tracks its state.

    ``url`` is anything serialx understands: a device path such as
    ``/dev/serial/by-id/...``, ``socket://host:port`` (ser2net raw TCP),
    ``rfc2217://host:port`` or ``esphome://...``.
    """

    def __init__(
        self,
        url: str,
        *,
        reconnect: bool = True,
        query_timeout: float = QUERY_TIMEOUT,
        connect_timeout: float = CONNECT_TIMEOUT,
    ) -> None:
        """Initialize the client without connecting."""
        self.url = url
        self.state = LumagenState()
        self._reconnect = reconnect
        self._query_timeout = query_timeout
        self._connect_timeout = connect_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._splitter = LineSplitter()
        self._write_lock = asyncio.Lock()
        self._query_lock = asyncio.Lock()
        self._pending: tuple[str, asyncio.Future[Message]] | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._closing = False
        self._connected = False
        self._full_info_query: str | None = None

        self._message_listeners: list[MessageListener] = []
        self._connection_listeners: list[ConnectionListener] = []

    # ---- Connection lifecycle -------------------------------------------

    @property
    def connected(self) -> bool:
        """Return True while the serial connection is open."""
        return self._connected

    async def connect(self) -> None:
        """Open the connection and start reading (and reconnecting) in the background."""
        if self._run_task is not None:
            raise LumagenError("Client is already started")
        self._closing = False
        await self._open()
        self._run_task = asyncio.create_task(self._run(), name=f"lumagen {self.url}")

    async def close(self) -> None:
        """Close the connection and stop reconnecting."""
        self._closing = True
        if self._run_task is not None:
            self._run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._run_task
            self._run_task = None
        writer = self._writer
        self._teardown()
        if writer is not None:
            with contextlib.suppress(*_SERIAL_ERRORS):
                await writer.wait_closed()

    async def _open(self) -> None:
        try:
            async with asyncio.timeout(self._connect_timeout):
                reader, writer = await serialx.open_serial_connection(self.url, baudrate=BAUDRATE)
        except (*_SERIAL_ERRORS, TimeoutError, ValueError) as err:
            raise LumagenConnectionError(f"Cannot open {self.url}: {err}") from err
        self._reader, self._writer = reader, writer
        self._splitter.reset()
        _LOGGER.debug("Connected to %s", self.url)
        self._set_connected(True)

    async def _run(self) -> None:
        while True:
            try:
                await self._read_loop()
            except _SERIAL_ERRORS as err:
                _LOGGER.warning("Lost connection to %s: %s", self.url, err)
            else:
                _LOGGER.warning("Connection to %s closed", self.url)
            self._teardown()
            if self._closing or not self._reconnect:
                return
            await self._reconnect_loop()
            if self._closing:
                return

    async def _reconnect_loop(self) -> None:
        attempt = 0
        while not self._closing:
            await asyncio.sleep(RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)])
            attempt += 1
            try:
                await self._open()
            except LumagenConnectionError as err:
                _LOGGER.debug("Reconnect attempt %s failed: %s", attempt, err)
            else:
                _LOGGER.info("Reconnected to %s", self.url)
                return

    async def _read_loop(self) -> None:
        reader = self._reader
        assert reader is not None
        while data := await reader.read(1024):
            for line in self._splitter.feed(data):
                self._handle_line(line)

    def _teardown(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._reader = self._writer = None
        if self._pending is not None and not self._pending[1].done():
            self._pending[1].set_exception(LumagenConnectionError("Connection lost"))
        self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        if self._closing:
            return  # Deliberate close; nobody needs to react.
        for listener in list(self._connection_listeners):
            listener(connected)

    # ---- Listeners --------------------------------------------------------

    def add_message_listener(self, listener: MessageListener) -> Callable[[], None]:
        """Call ``listener`` for every unsolicited report; returns an unsubscribe."""
        self._message_listeners.append(listener)
        return lambda: self._message_listeners.remove(listener)

    def add_connection_listener(self, listener: ConnectionListener) -> Callable[[], None]:
        """Call ``listener(connected)`` when the connection opens or drops."""
        self._connection_listeners.append(listener)
        return lambda: self._connection_listeners.remove(listener)

    # ---- Receiving --------------------------------------------------------

    def _handle_line(self, line: str) -> None:
        message = parse_line(line)
        if message is None:
            _LOGGER.debug("Ignoring line %r", line)
            return
        _LOGGER.debug("Received %s,%s", message.code, message.data)
        self.state.apply(message)
        pending = self._pending
        if pending is not None and pending[0] == message.code and not pending[1].done():
            pending[1].set_result(message)
            return
        for listener in list(self._message_listeners):
            listener(message)

    # ---- Sending ----------------------------------------------------------

    async def send(self, command: str) -> None:
        """Send a raw command string exactly as given."""
        writer = self._writer
        if writer is None or not self._connected:
            raise LumagenConnectionError("Not connected")
        _LOGGER.debug("Sending %r", command)
        async with self._write_lock:
            try:
                writer.write(command.encode("ascii"))
                await writer.drain()
            except _SERIAL_ERRORS as err:
                raise LumagenConnectionError(f"Write failed: {err}") from err

    async def query(self, query: str, timeout: float | None = None) -> Message:
        """Send a ``ZQ`` query and wait for its reply."""
        code = query_code(query)
        async with self._query_lock:
            future: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
            self._pending = (code, future)
            try:
                await self.send(query)
                async with asyncio.timeout(timeout or self._query_timeout):
                    return await future
            except TimeoutError as err:
                raise LumagenTimeoutError(f"No reply to {query}") from err
            finally:
                self._pending = None

    async def _query_optional(self, query: str) -> Message | None:
        try:
            return await self.query(query)
        except LumagenTimeoutError:
            _LOGGER.debug("No reply to optional query %s", query)
            return None

    # ---- High-level API ---------------------------------------------------

    async def get_identity(self) -> Identity:
        """Query model, firmware revision and serial number."""
        await self.query(commands.QUERY_IDENTITY)
        assert self.state.identity is not None
        return self.state.identity

    async def refresh(self) -> LumagenState:
        """Poll the processor; raises if it does not answer the power query."""
        if self.state.identity is None:
            await self._query_optional(commands.QUERY_IDENTITY)
        await self.query(commands.QUERY_POWER)
        if self.state.power:
            await self._refresh_full_info()
            await self._query_optional(commands.QUERY_INPUT_INFO)
            await self._query_optional(commands.QUERY_GAME_MODE)
        return self.state

    async def _refresh_full_info(self) -> None:
        if self._full_info_query is not None:
            await self._query_optional(self._full_info_query)
            return
        # Use the newest full-information query this firmware answers.
        for query in commands.QUERY_FULL_INFO:
            if await self._query_optional(query) is not None:
                self._full_info_query = query
                return

    async def refresh_labels(self, memory: str, count: int) -> dict[int, str]:
        """Read input labels 1..count (max 10) for a memory."""
        labels: dict[int, str] = {}
        for number in range(1, min(count, commands.MAX_LABELED_INPUTS) + 1):
            reply = await self._query_optional(commands.query_input_label(memory, number))
            if reply is not None and (label := reply.data.strip()):
                labels[number] = label
                self.state.labels[f"{memory.upper()}{number}"] = label
        return labels

    async def power_on(self) -> None:
        """Wake the processor (state is updated optimistically)."""
        await self.send(commands.POWER_ON)
        self.state.apply(Message("S02", "1"))

    async def standby(self) -> None:
        """Put the processor in standby (state is updated optimistically)."""
        await self.send(commands.STANDBY)
        self.state.apply(Message("S02", "0"))

    async def select_input(self, number: int) -> None:
        """Select input 1-19."""
        await self.send(commands.select_input(number))

    async def select_memory(self, memory: str) -> None:
        """Select input memory A-D."""
        await self.send(commands.select_memory(memory))

    async def set_game_mode(self, enabled: bool) -> None:
        """Turn game mode on or off."""
        await self.send(commands.set_game_mode(enabled))
        self.state.game_mode = enabled

    async def send_key(self, key: str) -> None:
        """Send a named key from ``commands.KEYS``."""
        try:
            command = commands.KEYS[key]
        except KeyError as err:
            raise ValueError(f"Unknown key {key!r}") from err
        await self.send(command)

    async def show_message(self, text: str, seconds: int = 3) -> None:
        """Show an on-screen message."""
        await self.send(commands.show_message(text, seconds))


async def async_probe(url: str) -> Identity:
    """Connect once, read the identity and disconnect (for setup validation)."""
    client = LumagenClient(url, reconnect=False)
    await client.connect()
    try:
        return await client.get_identity()
    finally:
        await client.close()
