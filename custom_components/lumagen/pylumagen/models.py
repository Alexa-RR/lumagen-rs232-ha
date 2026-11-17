"""Typed views of Lumagen query replies and the aggregated device state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .protocol import Message

# The ZQI2x refresh-rate fields are three digits with the fraction dropped
# ("059" means 59.94). Map the truncated NTSC-family rates back.
_FRACTIONAL_RATES = {
    23: 23.976,
    29: 29.97,
    47: 47.952,
    59: 59.94,
    71: 71.928,
    119: 119.88,
}


class InputStatus(IntEnum):
    """Field ``M`` of the full-information reply."""

    NO_SOURCE = 0
    ACTIVE_VIDEO = 1
    TEST_PATTERN = 2


class Colorspace(IntEnum):
    """Field ``E`` (output colorspace) of the full-information reply."""

    REC601 = 0
    REC709 = 1
    REC2020 = 2
    REC2100 = 3


def vertical_rate_to_hz(raw: int | None) -> float | None:
    """Convert a three-digit ZQI2x rate field to Hz."""
    if raw is None:
        return None
    return _FRACTIONAL_RATES.get(raw, float(raw))


def aspect_to_ratio(raw: int | None) -> float | None:
    """Convert an aspect field like ``240`` to ``2.40``."""
    if raw is None or raw == 0:
        return None
    return raw / 100


def _int(value: str | None, base: int = 10) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip(), base)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Identity:
    """Reply to ``ZQS01``."""

    model_name: str
    software_revision: str
    model_number: str
    serial_number: str

    @classmethod
    def from_message(cls, message: Message) -> Identity:
        """Parse ``!S01,RadianceXD,102308,1009,745``."""
        fields = [f.strip() for f in message.fields] + ["", "", "", ""]
        return cls(fields[0], fields[1], fields[2], fields[3])


@dataclass(frozen=True, slots=True)
class InputInfo:
    """Reply to ``ZQI00``: logical input, memory, physical input."""

    logical_input: int | None
    memory: str | None
    physical_input: int | None

    @classmethod
    def from_message(cls, message: Message) -> InputInfo:
        """Parse ``!I00,1,A,1``."""
        fields: list[str | None] = [*message.fields, None, None, None]
        memory = fields[1].strip().upper() if fields[1] else None
        return cls(_int(fields[0]), memory or None, _int(fields[2]))


# Field order of ZQI22/23/24. Later firmware may append more fields, so
# parsing must tolerate (and ignore) anything after the last known one.
_FULL_INFO_FIELDS = (
    "input_status",  # M
    "source_vertical_rate",  # RRR
    "source_vertical_resolution",  # VVVV
    "source_3d_mode",  # D
    "input_config",  # X
    "source_raster_aspect",  # AAA
    "source_content_aspect",  # SSS
    "nls_active",  # Y
    "output_3d_mode",  # T
    "outputs_on",  # WWWW (hex bitmask)
    "output_cms",  # C
    "output_style",  # B
    "output_vertical_rate",  # PPP
    "output_vertical_resolution",  # QQQQ
    "output_aspect",  # ZZZ
    "output_colorspace",  # E (I22+)
    "source_dynamic_range",  # F (I22+)
    "source_mode",  # G (I22+)
    "output_mode",  # H (I22+)
    "virtual_input",  # II (I23+)
    "physical_input",  # KK (I23+)
    "detected_raster_aspect",  # JJJ (I24+)
    "detected_content_aspect",  # LLL (I24+)
)

# ZQI21's documented format string omits T and WWWW even though its field list
# describes them, so accept both the 13- and 15-field variants.
_FULL_INFO_V1_SHORT = tuple(
    name for name in _FULL_INFO_FIELDS[:15] if name not in ("output_3d_mode", "outputs_on")
)


@dataclass(frozen=True, slots=True)
class FullInfo:
    """Reply to ``ZQI21``-``ZQI24`` (also sent unsolicited in "Full" report modes)."""

    input_status: InputStatus | None = None
    source_vertical_rate: int | None = None
    source_vertical_resolution: int | None = None
    source_3d_mode: int | None = None
    input_config: int | None = None
    source_raster_aspect: int | None = None
    source_content_aspect: int | None = None
    nls_active: bool | None = None
    output_3d_mode: int | None = None
    outputs_on: int | None = None
    output_cms: int | None = None
    output_style: int | None = None
    output_vertical_rate: int | None = None
    output_vertical_resolution: int | None = None
    output_aspect: int | None = None
    output_colorspace: Colorspace | None = None
    source_dynamic_range: int | None = None
    source_mode: str | None = None
    output_mode: str | None = None
    virtual_input: int | None = None
    physical_input: int | None = None
    detected_raster_aspect: int | None = None
    detected_content_aspect: int | None = None

    @classmethod
    def from_message(cls, message: Message) -> FullInfo:
        """Parse any of the ``!I21`` .. ``!I24`` replies."""
        fields = [f.strip() for f in message.fields]
        if message.code == "I21" and len(fields) < 15:
            names: tuple[str, ...] = _FULL_INFO_V1_SHORT
        else:
            names = _FULL_INFO_FIELDS
        raw = dict(zip(names, fields, strict=False))
        values: dict[str, object] = {}
        for name, value in raw.items():
            if name == "nls_active":
                values[name] = value.upper() == "N"
            elif name == "outputs_on":
                values[name] = _int(value, 16)
            elif name in ("source_mode", "output_mode"):
                values[name] = value.lower() if value and value != "-" else None
            elif name == "input_status":
                status = _int(value)
                values[name] = InputStatus(status) if status in (0, 1, 2) else None
            elif name == "output_colorspace":
                space = _int(value)
                values[name] = Colorspace(space) if space in (0, 1, 2, 3) else None
            else:
                values[name] = _int(value)
        return cls(**values)  # type: ignore[arg-type]

    @property
    def has_source(self) -> bool:
        """Return True when a source (or internal pattern) is active."""
        return self.input_status in (InputStatus.ACTIVE_VIDEO, InputStatus.TEST_PATTERN)

    @property
    def is_hdr(self) -> bool | None:
        """Return True when the source is HDR (needs ZQI22 or newer)."""
        if self.source_dynamic_range is None:
            return None
        return self.source_dynamic_range == 1

    @property
    def source_frame_rate(self) -> float | None:
        """Source refresh rate in Hz."""
        return vertical_rate_to_hz(self.source_vertical_rate) if self.has_source else None

    @property
    def output_frame_rate(self) -> float | None:
        """Output refresh rate in Hz."""
        return vertical_rate_to_hz(self.output_vertical_rate)

    @property
    def source_resolution(self) -> str | None:
        """Source resolution like ``2160p`` (``p`` assumed before ZQI22)."""
        if not self.has_source or not self.source_vertical_resolution:
            return None
        return f"{self.source_vertical_resolution}{self.source_mode or 'p'}"

    @property
    def output_resolution(self) -> str | None:
        """Output resolution like ``2160p``."""
        if not self.output_vertical_resolution:
            return None
        return f"{self.output_vertical_resolution}{self.output_mode or 'p'}"


@dataclass(frozen=True, slots=True)
class SourceAspect:
    """Reply to ``ZQI20``."""

    index: int | None
    nls: bool

    @classmethod
    def from_message(cls, message: Message) -> SourceAspect:
        """Parse ``!I20,2-``."""
        value = message.data.strip()
        return cls(_int(value[:1]), value[1:2].upper() == "N")


@dataclass
class LumagenState:
    """Everything the client has learned about the processor so far."""

    power: bool | None = None
    identity: Identity | None = None
    full_info: FullInfo | None = None
    input_info: InputInfo | None = None
    source_aspect: SourceAspect | None = None
    game_mode: bool | None = None
    labels: dict[str, str] = field(default_factory=dict)
    """Input labels keyed by memory + input number, e.g. ``"A1"``."""

    @property
    def current_input(self) -> int | None:
        """The input selected by remote/RS-232 (virtual input on a Pro)."""
        if self.full_info is not None and self.full_info.virtual_input:
            return self.full_info.virtual_input
        if self.input_info is not None:
            return self.input_info.logical_input
        return None

    @property
    def current_memory(self) -> str | None:
        """The active input memory, ``A``-``D``."""
        return self.input_info.memory if self.input_info is not None else None

    def input_label(self, number: int, memory: str | None = None) -> str | None:
        """Return the label for an input in the given (or current) memory."""
        memory = memory or self.current_memory or "A"
        return self.labels.get(f"{memory}{number}")

    def apply(self, message: Message) -> None:
        """Update the state from one reply or unsolicited report."""
        code = message.code
        if code == "S02":
            self.power = message.data.strip() == "1"
            if not self.power:
                # Video status is meaningless in standby.
                self.full_info = None
                self.source_aspect = None
        elif code == "S01":
            self.identity = Identity.from_message(message)
        elif code in ("I21", "I22", "I23", "I24"):
            self.full_info = FullInfo.from_message(message)
            # Only an awake unit reports video status.
            self.power = True
        elif code == "I00":
            self.input_info = InputInfo.from_message(message)
        elif code == "I20":
            self.source_aspect = SourceAspect.from_message(message)
        elif code == "I53":
            self.game_mode = message.data.strip() == "1"
