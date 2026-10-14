"""Dutch postcode normalisation.

A PC6 is four digits and two letters. The official written form has a
space (``1011 AA``); the in-memory key does not (``1011AA``).
"""

from __future__ import annotations

import re

_PC6 = re.compile(r"^[1-9][0-9]{3}[A-Z]{2}$")


def normalise_postcode(postcode: str) -> str:
    """Return ``postcode`` as a PC6 key.

    Spaces are removed and letters are uppercased. ``"1011 aa"``,
    ``"1011 AA"`` and ``"1011AA"`` all return ``"1011AA"``.

    Raises:
        ValueError: ``postcode`` is not a Dutch postcode of four digits
            and two letters. The first digit is never zero.
    """
    if not isinstance(postcode, str):
        raise TypeError(f"postcode must be a str, got {type(postcode).__name__}")
    compact = "".join(postcode.split()).upper()
    if _PC6.fullmatch(compact) is None:
        raise ValueError(f"not a Dutch postcode: {postcode!r}")
    return compact
