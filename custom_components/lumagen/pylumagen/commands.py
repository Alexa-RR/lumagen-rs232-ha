"""Command strings from Lumagen Tech Tip 11.

Assumes RS-232 Delimiter Mode = Off (Lumagen's recommended setting). In
delimiter mode ``~`` becomes ``?`` and ``#`` becomes ``:``.
"""

from __future__ import annotations

CR = "\r"

POWER_ON = "%"
STANDBY = "$"

# Queries (no terminator).
QUERY_ALIVE = "ZQS00"
QUERY_IDENTITY = "ZQS01"
QUERY_POWER = "ZQS02"
QUERY_INPUT_INFO = "ZQI00"
QUERY_SOURCE_ASPECT = "ZQI20"
QUERY_GAME_MODE = "ZQI53"
# Newest first; the client uses the first one the firmware answers.
QUERY_FULL_INFO = ("ZQI24", "ZQI23", "ZQI22", "ZQI21")

MEMORIES = ("A", "B", "C", "D")
MAX_INPUTS = 19
# The label query takes the input as one character, so only 1-10 are addressable.
MAX_LABELED_INPUTS = 10

# Remote keys and other single/multi-character commands that take no <CR>.
KEYS: dict[str, str] = {
    "power_on": POWER_ON,
    "standby": STANDBY,
    "menu": "M",
    "exit": "X",
    "help": "U",
    "clear": "!",
    "alt": "#",
    "previous_input": "P",
    "zone": "L",
    "ok": "k",
    "left": "<",
    "right": ">",
    "up": "^",
    "down": "v",
    **{str(digit): str(digit) for digit in range(10)},
    "plus_10": "+",
    "pip_off": "e",
    "pip_select": "p",
    "pip_swap": "r",
    "pip_mode": "m",
    "nls": "N",
    "memory_a": "a",
    "memory_b": "b",
    "memory_c": "c",
    "memory_d": "d",
    "osd_on": "g",
    "osd_off": "s",
    "auto_aspect_on": "~",
    "auto_aspect_off": "V",
    "hdr_setup": "Y",
    "test_pattern": "H",
    "save": "Sk",
    # Source aspects. "_nz" variants select the aspect with no zoom.
    "aspect_4_3": "n",
    "aspect_4_3_nz": "[",
    "aspect_4_3_nls": "[N",
    "aspect_letterbox": "l",
    "aspect_letterbox_nz": "]",
    "aspect_letterbox_nls": "]N",
    "aspect_16_9": "w",
    "aspect_16_9_nz": "*",
    "aspect_16_9_nls": "*N",
    "aspect_1_85": "j",
    "aspect_1_85_nz": "/",
    "aspect_1_85_nls": "/N",
    "aspect_1_90": "A",
    "aspect_1_90_nls": "AN",
    "aspect_2_00": "C",
    "aspect_2_00_nls": "CN",
    "aspect_2_20": "E",
    "aspect_2_20_nls": "EN",
    "aspect_2_35": "W",
    "aspect_2_35_nz": "K",
    "aspect_2_40": "G",
    # Need Input > Options > Aspect Setup > Aspect Opts = Extended.
    "aspect_4_3_pillarbox": "+n",
    "aspect_1_375_pillarbox": "+l",
    "aspect_1_66_pillarbox": "+w",
    "aspect_2_10": "+j",
    "aspect_2_55": "+W",
    "aspect_2_76": "+N",
}


def select_input(number: int) -> str:
    """Return the command for input 1-19 (``+`` adds 10 to the next digit)."""
    if not 1 <= number <= MAX_INPUTS:
        raise ValueError(f"Input must be 1-{MAX_INPUTS}, got {number}")
    return f"i{number}" if number < 10 else f"i+{number - 10}"


def select_memory(memory: str) -> str:
    """Return the command for input memory A-D."""
    memory = memory.upper()
    if memory not in MEMORIES:
        raise ValueError(f"Memory must be one of {MEMORIES}, got {memory!r}")
    return memory.lower()


def set_game_mode(enabled: bool) -> str:
    """Return the command to turn game mode on or off (Radiance Pro)."""
    return f"ZY551{int(enabled)}{CR}"


def query_input_label(memory: str, number: int) -> str:
    """Return the label query for an input (1-10) in memory A-D."""
    if not 1 <= number <= MAX_LABELED_INPUTS:
        raise ValueError(f"Labels can only be read for inputs 1-{MAX_LABELED_INPUTS}")
    return f"ZQS1{select_memory(memory).upper()}{number - 1}"


def show_message(text: str, seconds: int = 3) -> str:
    """Return the command to show an on-screen message.

    ``seconds`` is 0-8; 9 keeps the message up until it is cleared. The
    processor shows two lines of 30 characters and only accepts 0x20-0x7A.
    """
    if not 0 <= seconds <= 9:
        raise ValueError("seconds must be 0-9")
    clean = "".join(ch if " " <= ch <= "z" else " " for ch in text)[:60]
    return f"ZT{seconds}{clean}{CR}"


CLEAR_MESSAGE = "ZC"
