"""Low-level framing for the Lumagen RS-232 protocol (Tech Tip 11).

Wire format summary:

* Remote-key commands are single characters (``%`` power on, ``i3`` input 3) and
  must NOT be followed by a carriage return; a stray ``<CR>`` opens the Info page.
* ``ZY``/``ZT``/``ZW`` style commands end with ``<CR>`` (or ``{``).
* Queries are ``ZQ`` + ``I``/``S``/``O`` + two characters, with no terminator.
* Replies are ``!`` + the last three characters of the query + ``,data`` + CRLF,
  e.g. ``ZQS02`` -> ``!S02,1``. Label queries (``ZQS1B5``) are the exception and
  answer with ``!S1B,...`` - i.e. characters 2-5 of the query.
* With Echo = On (the factory default) every character sent is echoed back, so
  echoed command text ends up glued to the front of the next reply line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Leftmost "!<letter><digit><char>," - the echo of our own commands never
# contains that sequence, but may contain a bare "!" (the CLR key).
_RESPONSE_RE = re.compile(r"!([IOS][0-9][0-9A-Z]),(.*)$")
_LINE_SPLIT_RE = re.compile(rb"[\r\n]")

# Keep a partial line from growing without bound when only echo arrives.
_MAX_BUFFER = 1024


@dataclass(frozen=True, slots=True)
class Message:
    """One reply or unsolicited report from the processor."""

    code: str
    """Three-character code, e.g. ``S02``, ``I24`` or ``S1B``."""
    data: str
    """Everything after the first comma, unsplit (labels may contain commas)."""

    @property
    def fields(self) -> list[str]:
        """Comma-separated fields of the payload."""
        return self.data.split(",")


def query_code(query: str) -> str:
    """Return the reply code a query will be answered with."""
    if len(query) < 5 or not query.startswith("ZQ"):
        raise ValueError(f"Not a Lumagen query: {query!r}")
    return query[2:5]


def parse_line(line: str) -> Message | None:
    """Extract a reply from one received line, ignoring echoed command text."""
    match = _RESPONSE_RE.search(line)
    if match is None:
        return None
    return Message(code=match[1], data=match[2].rstrip())


class LineSplitter:
    """Split the received byte stream into lines on CR and/or LF."""

    def __init__(self) -> None:
        """Initialize an empty buffer."""
        self._buffer = bytearray()

    def reset(self) -> None:
        """Drop any partial line (used after reconnecting)."""
        self._buffer.clear()

    def feed(self, data: bytes) -> list[str]:
        """Add received bytes and return every completed, non-empty line."""
        self._buffer.extend(data)
        *complete, rest = _LINE_SPLIT_RE.split(bytes(self._buffer))
        self._buffer = bytearray(rest[-_MAX_BUFFER:])
        return [bytes(b & 0x7F for b in chunk).decode("ascii") for chunk in complete if chunk]
