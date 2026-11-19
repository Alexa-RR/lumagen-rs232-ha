"""Parsing tests against the formats in Tech Tip 11."""

from __future__ import annotations

import pytest

from custom_components.lumagen.pylumagen import (
    Colorspace,
    FullInfo,
    Identity,
    InputInfo,
    InputStatus,
    LineSplitter,
    LumagenState,
    SourceAspect,
    commands,
    parse_line,
)
from custom_components.lumagen.pylumagen.protocol import query_code

from .fake_lumagen import I24_4K_HDR


def test_splitter_handles_crlf_lfcr_and_partial_lines() -> None:
    splitter = LineSplitter()
    assert splitter.feed(b"ZQS02!S02,1\r\n!Y\n\r!I0") == ["ZQS02!S02,1", "!Y"]
    assert splitter.feed(b"0,1,A,1\r\n") == ["!I00,1,A,1"]


def test_splitter_masks_high_bit_and_bounds_buffer() -> None:
    splitter = LineSplitter()
    assert splitter.feed(bytes([0x21, 0xD3, 0x30, 0x32, 0x2C, 0x31, 0x0D])) == ["!S02,1"]
    splitter.feed(b"%" * 5000)
    assert splitter.feed(b"\r") == ["%" * 1024]


@pytest.mark.parametrize(
    ("line", "code", "data"),
    [
        ("!S02,1", "S02", "1"),
        # Echo of our own query glued to the front of the reply.
        ("ZQI00!I00,1,A,1", "I00", "1,A,1"),
        # Echo of the CLR key ("!") before a query must not confuse the parser.
        ("!ZQS02!S02,0", "S02", "0"),
        ("ZQS1B5!S1B,Input 6B", "S1B", "Input 6B"),
        ("!I01,1,5992,720,480,1,0 ", "I01", "1,5992,720,480,1,0"),
    ],
)
def test_parse_line(line: str, code: str, data: str) -> None:
    message = parse_line(line)
    assert message is not None
    assert (message.code, message.data) == (code, data)


@pytest.mark.parametrize("line", ["", "%$ik", "!Y", "!N", "garbage!"])
def test_parse_line_ignores_non_replies(line: str) -> None:
    assert parse_line(line) is None


def test_query_code() -> None:
    assert query_code("ZQS02") == "S02"
    assert query_code("ZQI24") == "I24"
    assert query_code("ZQS1B5") == "S1B"
    with pytest.raises(ValueError):
        query_code("%")


def test_identity() -> None:
    identity = Identity.from_message(parse_line("!S01,RadianceXD,102308,1009,745"))
    assert identity == Identity("RadianceXD", "102308", "1009", "745")


def test_input_info() -> None:
    assert InputInfo.from_message(parse_line("!I00,12,b,4")) == InputInfo(12, "B", 4)


def test_source_aspect() -> None:
    assert SourceAspect.from_message(parse_line("!I20,9N")) == SourceAspect(9, True)
    assert SourceAspect.from_message(parse_line("!I20,2-")) == SourceAspect(2, False)


def test_full_info_v4() -> None:
    info = FullInfo.from_message(parse_line("!" + I24_4K_HDR))
    assert info.input_status is InputStatus.ACTIVE_VIDEO
    assert info.source_frame_rate == 23.976
    assert info.source_resolution == "2160p"
    assert info.source_content_aspect == 240
    assert info.nls_active is False
    assert info.outputs_on == 1
    assert info.output_cms == 1
    assert info.output_style == 2
    assert info.output_resolution == "2160p"
    assert info.output_colorspace is Colorspace.REC2100
    assert info.is_hdr is True
    assert (info.virtual_input, info.physical_input) == (3, 2)
    assert info.detected_content_aspect == 240


def test_full_info_v5_from_radiance_pro() -> None:
    # A real ZQI25 reply shape (1080p59.94 SDR on input 1, memory A).
    info = FullInfo.from_message(
        parse_line(
            "!I25,1,059,1080,0,0,178,178,-,0,000E,0,0,059,2160,185,2,0,p,P,1,01,178,178,A,0,0,2"
        )
    )
    assert info.source_frame_rate == 59.94
    assert info.source_resolution == "1080p"
    assert info.output_resolution == "2160p"
    assert info.outputs_on == 0x0E
    assert info.physical_input == 1
    assert info.input_memory == "A"
    assert (info.sub_shift, info.auto_aspect) == (0, 2)


def test_state_takes_memory_from_full_info() -> None:
    state = LumagenState()
    state.apply(parse_line("!I00,1,A,1"))
    state.apply(
        parse_line(
            "!I25,1,059,1080,0,0,178,178,-,0,000E,0,0,059,2160,185,2,0,p,P,1,01,178,178,C,0,0,2"
        )
    )
    assert state.current_memory == "C"


def test_full_info_tolerates_future_fields() -> None:
    info = FullInfo.from_message(parse_line("!" + I24_4K_HDR + ",X,Y,Z"))
    assert info.detected_content_aspect == 240


def test_full_info_v2_has_no_input_fields() -> None:
    info = FullInfo.from_message(
        parse_line("!I22,1,059,1080,0,1,178,178,N,0,0003,0,0,060,2160,178,1,0,i,P")
    )
    assert info.source_frame_rate == 59.94
    assert info.source_resolution == "1080i"
    assert info.nls_active is True
    assert info.virtual_input is None
    assert info.is_hdr is False


def test_full_info_v1_short_form() -> None:
    # The documented 13-field ZQI21 format (no T / WWWW).
    info = FullInfo.from_message(parse_line("!I21,1,060,1080,0,0,178,185,-,3,4,060,1080,178"))
    assert info.output_cms == 3
    assert info.output_style == 4
    assert info.outputs_on is None
    assert info.is_hdr is None
    assert info.source_resolution == "1080p"


def test_no_source_hides_source_values() -> None:
    info = FullInfo.from_message(
        parse_line("!I24,0,000,0000,0,0,000,000,-,0,0001,0,0,060,2160,178,1,0,-,P,1,1,000,000")
    )
    assert info.has_source is False
    assert info.source_resolution is None
    assert info.source_frame_rate is None
    assert info.output_frame_rate == 60.0


def test_state_standby_clears_video_status() -> None:
    state = LumagenState()
    state.apply(parse_line("!" + I24_4K_HDR))
    assert state.power is True
    assert state.current_input == 3
    state.apply(parse_line("!S02,0"))
    assert state.power is False
    assert state.full_info is None


def test_commands() -> None:
    assert commands.select_input(3) == "i3"
    assert commands.select_input(10) == "i+0"
    assert commands.select_input(12) == "i+2"
    with pytest.raises(ValueError):
        commands.select_input(20)
    assert commands.select_memory("c") == "c"
    assert commands.set_game_mode(True) == "ZY5511\r"
    assert commands.query_input_label("b", 6) == "ZQS1B5"
    assert commands.show_message("Hi{there}", 9) == "ZT9Hi there \r"
    assert len(commands.show_message("x" * 100)) == 2 + 1 + 60 + 1
