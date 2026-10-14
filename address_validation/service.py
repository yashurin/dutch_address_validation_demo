"""Format and validate Dutch addresses against an in-memory repository.

A successful lookup is the two-line form used on Dutch mail, with exactly
two spaces before the city::

    De Ruyterkade Steigers 7A
    1011 AA  AMSTERDAM

:meth:`AddressService.lookup_address` returns those two strings, or an
empty list when the postcode and house number are not in the reference
data. :meth:`AddressService.validate_lines` parses that same shape and
calls :meth:`AddressService.validate`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from address_validation.loader import create_repository
from address_validation.models import (
    PO_BOX_STREET,
    REPLY_STREET,
    HouseNumberRange,
    InMemoryRepository,
    SeriesKind,
)
from address_validation.normalise import (
    normalise_extension,
    normalise_name,
    resolve_house_number,
)
from address_validation.postcode import format_postcode, normalise_postcode
from address_validation.suggest import SuggestionIndex

_STREET_LINE = re.compile(
    r"^(?P<street>.*\S)\s+(?P<number>\d+)\s*[-/]?\s*(?P<extension>.*)$",
)
_POSTCODE_LINE = re.compile(
    r"^(?P<postcode>\d{4}\s*[A-Za-z]{2})\s+(?P<city>\S(?:.*\S)?)\s*$",
)


class AddressService:
    """Look up and validate addresses in a loaded PCS repository.

    Postcode spelling is flexible (``"1011AA"``, ``"1011 aa"``,
    ``"1011 AA"``). House-number parity follows the range: an even number
    does not match an odd series. Extensions are optional. The PCS files
    have no toevoeging column, so a well-formed extension is accepted and
    repeated on the formatted line; it is not checked against a list of
    known additions.

    The normalisation helpers are :meth:`normalise_postcode`,
    :meth:`format_postcode`, :meth:`normalise_name` and
    :meth:`normalise_extension`. :meth:`correct_city` and
    :meth:`correct_street` suggest published spellings for a mistyped name.
    """

    def __init__(self, repository: InMemoryRepository) -> None:
        self.repository = repository
        self._suggestion_index: SuggestionIndex | None = None

    @classmethod
    def load(cls, data_dir: str | Path = "data") -> AddressService:
        """Load the three PCS files and return a service for that data."""
        return cls(create_repository(data_dir))

    @staticmethod
    def normalise_postcode(postcode: str) -> str:
        """Return the PC6 key ``"1011AA"``. Spaces are removed."""
        return normalise_postcode(postcode)

    @staticmethod
    def format_postcode(postcode: str) -> str:
        """Return the written postcode ``"1011 AA"``."""
        return format_postcode(postcode)

    @staticmethod
    def normalise_name(name: str) -> str:
        """Fold a street or city for comparison.

        Case is ignored, whitespace is collapsed, and apostrophe variants
        are treated as the same character.
        """
        return normalise_name(name)

    @staticmethod
    def normalise_extension(extension: str | None) -> str | None:
        """Return a canonical toevoeging, or ``None`` when it is blank.

        ``"a"`` and ``"-A"`` become ``"A"``. ``"BIS"`` becomes ``"bis"``.
        ``None``, ``""`` and ``"-"`` become ``None``.
        """
        return normalise_extension(extension)

    def lookup_address(
        self,
        postcode: str,
        house_number: int | str,
        extension: str | None = None,
    ) -> list[str]:
        """Return ``[street_line, city_line]``, or ``[]`` when unknown.

        ``city_line`` is the postcode, two spaces, and the city in the
        published spelling (``"1011 AA  AMSTERDAM"``). A single-letter
        extension is glued to the house number (``"7A"``). Any other
        extension is joined with a hyphen (``"7-bis"``).

        Postbus and antwoordnummer rows have no street in the files. They
        are formatted as ``"Postbus 25"`` and ``"Antwoordnummer 5"``.
        A numberless range (house number 0) is formatted as the street
        name alone; an extension on that call is accepted and not printed.

        The result is ``[]`` when the postcode or house number is not in
        the data, the extension is not well-formed, or more than one
        street contains that house number. Parity is respected: ``4`` does
        not match a range of odd numbers.
        """
        try:
            number, addition = resolve_house_number(house_number, extension)
            matches = self.repository.matching_ranges(postcode, number)
            labels = self._labels(matches)
        except (TypeError, ValueError):
            return []
        if len(labels) != 1:
            return []
        street, city, numberless = labels.pop()
        if numberless:
            street_line = street
        else:
            street_line = format_street_line(street, number, addition)
        return [street_line, format_city_line(postcode, city)]

    def validate(
        self,
        street: str,
        house_number: int | str,
        extension: str | None,
        postcode: str,
        city: str,
    ) -> bool:
        """Return whether this address occurs in the reference data.

        ``street`` and ``city`` are compared with :meth:`normalise_name`,
        so ``"amsterdam"`` matches ``"AMSTERDAM"``. The house number must
        fall inside a range for ``postcode``, using that range's odd/even
        parity. ``extension`` may be omitted or written as ``"A"``,
        ``"-a"`` or ``"bis"``; a malformed extension makes the address
        invalid. Postbus and antwoordnummer addresses use those words as
        the street.
        """
        try:
            number, _addition = resolve_house_number(house_number, extension)
            street_key = normalise_name(street)
            city_key = normalise_name(city)
            matches = self.repository.matching_ranges(postcode, number)
        except (TypeError, ValueError):
            return False
        for street_name, city_name, _numberless in self._labels(matches):
            if (
                normalise_name(street_name) == street_key
                and normalise_name(city_name) == city_key
            ):
                return True
        return False

    def validate_lines(self, lines: list[str]) -> bool:
        """Parse a two-line address and return :meth:`validate`.

        Blank lines are ignored. After that, exactly two lines are
        required. The first line is ``"Street 12A"`` (also ``"12-A"`` or
        ``"12 bis"``). A line with no house number is read as house number
        0, which is how numberless ranges are written. The second line is
        a postcode and a city, separated by one or more spaces; the
        formatted form uses two.
        """
        parsed = parse_address_lines(lines)
        if parsed is None:
            return False
        street, house_number, extension, postcode, city = parsed
        return self.validate(street, house_number, extension, postcode, city)

    def correct_city(self, city: str, postcode: str | None = None) -> list[str]:
        """Return ranked, unique city suggestions for a mistyped name.

        Each suggestion is the published spelling (``"AMSTERDAM"``). Names
        are compared after :meth:`normalise_name`, so case, spacing and
        apostrophes do not matter. Results are best match first. Equal
        scores are ordered by casefolded name. At most five names at or
        above the difflib cutoff of 0.6 are returned. An empty name, an
        unusable postcode, or no close match returns ``[]``.

        ``postcode`` limits the candidates:

        * a PC6 (``"1011 AA"`` or ``"1011AA"``) uses only the cities on
          that postcode, almost always one;
        * a PC4 (``"1011"``) uses the cities in that district;
        * ``None`` scores every city. There are about 2,500, so this stays
          in the milliseconds.

        The first correction on a service builds an index over the
        repository. Later calls reuse it.
        """
        return self._suggestions().correct_city(self.repository, city, postcode)

    def correct_street(self, street: str, postcode: str | None = None) -> list[str]:
        """Return ranked, unique street suggestions for a mistyped name.

        Same ranking rules as :meth:`correct_city`: published spelling,
        best score first, at most five names with a difflib ratio of at
        least 0.6. ``"Postbus"`` and ``"Antwoordnummer"`` are included
        when that series occurs in the searched postcodes, and on every
        unscoped search, because those rows have no street in the file.

        Pass a postcode when you have one. A PC6 scores only the streets
        on that postcode (usually one or two). A PC4 scores the streets
        in that district, a few dozen on average and a few hundred in the
        busiest districts. With ``postcode=None`` every distinct street
        name is scored, about 138,000 of them, which takes a few hundred
        milliseconds. City correction does not have that cost.

        An empty name, an unusable postcode, or no close match returns
        ``[]``. The index built by the first correction call is reused.
        """
        return self._suggestions().correct_street(self.repository, street, postcode)

    def _suggestions(self) -> SuggestionIndex:
        index = self._suggestion_index
        if index is None:
            index = SuggestionIndex.build(self.repository)
            self._suggestion_index = index
        return index

    def _labels(
        self,
        matches: list[HouseNumberRange],
    ) -> set[tuple[str, str, bool]]:
        """Unique ``(street, city, numberless)`` labels for ``matches``.

        A missing street or city drops that row. Postbus and
        antwoordnummer use fixed street words because the files store
        street id 0 for them.
        """
        labels: set[tuple[str, str, bool]] = set()
        for match in matches:
            city = self.repository.city_name(match.city_id)
            if city is None:
                continue
            if match.kind is SeriesKind.PO_BOX:
                labels.add((PO_BOX_STREET, city, False))
                continue
            if match.kind is SeriesKind.REPLY_NUMBER:
                labels.add((REPLY_STREET, city, False))
                continue
            street = self.repository.street_name(match.street_id)
            if street is None:
                continue
            labels.add((street, city, match.kind is SeriesKind.NO_HOUSE_NUMBER))
        return labels


def format_street_line(street: str, house_number: int, extension: str | None) -> str:
    """Return ``"Straat 12"``, ``"Straat 12A"`` or ``"Straat 12-bis"``."""
    if extension is None:
        return f"{street} {house_number}"
    if len(extension) == 1 and extension.isalpha():
        return f"{street} {house_number}{extension}"
    return f"{street} {house_number}-{extension}"


def format_city_line(postcode: str, city: str) -> str:
    """Return ``"1011 AA  AMSTERDAM"``, with two spaces before the city."""
    return f"{format_postcode(postcode)}  {city}"


def parse_address_lines(
    lines: Sequence[str],
) -> tuple[str, int, str | None, str, str] | None:
    """Parse two address lines into street, number, extension, postcode, city.

    Returns ``None`` when ``lines`` is not a two-line address. A street
    line without a house number yields house number ``0`` and no extension.
    The last number on the street line is the house number, so a street
    such as ``"Laan 1945 10"`` keeps ``"Laan 1945"`` as the name.
    """
    if isinstance(lines, str) or not isinstance(lines, Sequence):
        return None
    content: list[str] = []
    for line in lines:
        if not isinstance(line, str):
            return None
        stripped = line.strip()
        if stripped:
            content.append(stripped)
    if len(content) != 2:
        return None
    try:
        street, house_number, extension = _parse_street_line(content[0])
        postcode, city = _parse_postcode_line(content[1])
    except ValueError:
        return None
    return street, house_number, extension, postcode, city


def _parse_street_line(line: str) -> tuple[str, int, str | None]:
    match = _STREET_LINE.fullmatch(line)
    if match is None:
        if line.strip() == "":
            raise ValueError("empty street line")
        return line.strip(), 0, None
    street = match.group("street").strip()
    if street == "":
        raise ValueError("missing street")
    number = int(match.group("number"))
    extension = normalise_extension(match.group("extension"))
    return street, number, extension


def _parse_postcode_line(line: str) -> tuple[str, str]:
    match = _POSTCODE_LINE.fullmatch(line)
    if match is None:
        raise ValueError(f"invalid postcode line {line!r}")
    # Reject a postcode that is only the right shape locally but not a PC6,
    # for example a leading zero. format/normalise is the shared check.
    normalise_postcode(match.group("postcode"))
    return match.group("postcode"), match.group("city").strip()
