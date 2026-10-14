"""Normalisation helpers for street names, cities, and house numbers.

Postcode helpers live in :mod:`address_validation.postcode`. Street and
city comparison uses :func:`normalise_name`. House-number extensions are
not stored in the PCS files; :func:`normalise_extension` only decides
whether a caller-supplied toevoeging is well-formed.
"""

from __future__ import annotations

import re

from address_validation.models import MAX_HOUSE_NUMBER

_APOSTROPHES = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u2032": "'",
        "`": "'",
    }
)
_HOUSE_NUMBER = re.compile(
    r"^(?P<number>\d+)\s*[-/]?\s*(?P<extension>.*)$",
)
_EXTENSION = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
_MAX_EXTENSION_LENGTH = 8


def normalise_name(name: str) -> str:
    """Fold a street or city name for comparison.

    The result is casefolded, with whitespace collapsed to single spaces
    and apostrophe variants (``'``, ``’``, ``‘``) folded to ``'``.
    ``"  De   Ruyterkade "`` and ``"de ruyterkade"`` both become
    ``"de ruyterkade"``.

    Raises:
        ValueError: ``name`` is empty after stripping.
    """
    if not isinstance(name, str):
        raise TypeError(f"name must be a str, got {type(name).__name__}")
    folded = " ".join(name.translate(_APOSTROPHES).split())
    if folded == "":
        raise ValueError("name is empty")
    return folded.casefold()


def normalise_extension(extension: str | None) -> str | None:
    """Return a canonical toevoeging, or ``None`` when it is absent.

    ``None``, ``""``, ``"-"`` and ``"/"`` are absent. A single letter is
    uppercased (``"a"`` becomes ``"A"``). Any longer token is casefolded
    (``"BIS"`` becomes ``"bis"``). Leading hyphens and slashes are
    removed. Internal spaces are rejected. At most 8 characters.

    Raises:
        ValueError: The extension is not a short letter, digit, or
            hyphenated token.
    """
    if extension is None:
        return None
    if not isinstance(extension, str):
        raise TypeError(
            f"extension must be a str or None, got {type(extension).__name__}"
        )
    text = " ".join(extension.split())
    text = text.strip("-/")
    if text == "":
        return None
    if " " in text or len(text) > _MAX_EXTENSION_LENGTH:
        raise ValueError(f"invalid extension {extension!r}")
    if _EXTENSION.fullmatch(text) is None:
        raise ValueError(f"invalid extension {extension!r}")
    if len(text) == 1 and text.isalpha():
        return text.upper()
    return text.casefold()


def resolve_house_number(
    house_number: int | str,
    extension: str | None = None,
) -> tuple[int, str | None]:
    """Return ``(house_number, extension)`` from either calling convention.

    ``12`` and ``"12"`` are the same number. ``"12A"``, ``"12-A"`` and
    ``"12 A"`` are number 12 with extension ``"A"``. When ``extension`` is
    also passed, it must agree with a suffix embedded in ``house_number``
    (``"12a"`` with ``"A"`` agrees; ``"12a"`` with ``"B"`` does not).

    Raises:
        ValueError: The number or extension cannot be read, or the two
            extension spellings disagree.
    """
    number, embedded = _split_house_number(house_number)
    explicit = normalise_extension(extension)
    if embedded is not None and explicit is not None and embedded != explicit:
        raise ValueError(
            f"extension {extension!r} does not match house number {house_number!r}"
        )
    return number, explicit if explicit is not None else embedded


def _split_house_number(house_number: int | str) -> tuple[int, str | None]:
    if isinstance(house_number, bool):
        raise TypeError("house_number must be an int or str, not bool")
    if isinstance(house_number, int):
        if house_number < 0 or house_number > MAX_HOUSE_NUMBER:
            raise ValueError(f"house number out of range: {house_number}")
        return house_number, None
    if not isinstance(house_number, str):
        raise TypeError(
            f"house_number must be an int or str, got {type(house_number).__name__}"
        )
    match = _HOUSE_NUMBER.fullmatch(house_number.strip())
    if match is None:
        raise ValueError(f"invalid house number {house_number!r}")
    number = int(match.group("number"))
    if number > MAX_HOUSE_NUMBER:
        raise ValueError(f"house number out of range: {number}")
    return number, normalise_extension(match.group("extension"))
