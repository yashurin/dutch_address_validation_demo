"""Domain model for the Dutch postcode reference data.

House-number ranges are the unit of validation. A range never stores a
street or city name: those live once each in the id indexes on
:class:`InMemoryRepository`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, IntEnum
from types import MappingProxyType

from address_validation.postcode import normalise_postcode

# House numbers in PCS_HNR.dat are at most five digits (0 .. 99999).
MAX_HOUSE_NUMBER = 99_999


class SeriesKind(IntEnum):
    """Column 1 of ``PCS_HNR.dat``: what the numeric span refers to.

    Postbus and antwoordnummer rows share an empty street id. The kind is
    the only field that tells those two products apart.
    """

    STREET = 1
    PO_BOX = 2
    REPLY_NUMBER = 3
    NO_HOUSE_NUMBER = 4


# Street words for ranges that have no row in PCS_STR.dat. Lookup and
# street correction both use these spellings.
PO_BOX_STREET = "Postbus"
REPLY_STREET = "Antwoordnummer"


class Parity(Enum):
    """Which integers inside ``[from_number, to_number]`` belong to the range.

    The value is the code from ``PCS_HNR.dat``. A blank field is
    :attr:`ALL`.

    ``ODD``, ``EVEN`` and ``DOORLOPEND`` all step by two, starting at
    ``from_number``. ``D`` (doorlopend) means the street is numbered
    consecutively rather than odd-on-one-side, even-on-the-other. The file
    still emits that street as one odd row and one even row, so a ``D``
    range does not contain both parities.

    ``ALL`` (blank in the file) contains every integer. That is how postbus
    and antwoordnummer spans are stored: ``1``–``49`` contains 1, 2, 3, …
    ``NO_NUMBER`` (``G``) is the span ``0``–``0``: the postcode has no
    house number.
    """

    ODD = "O"
    EVEN = "E"
    DOORLOPEND = "D"
    NO_NUMBER = "G"
    ALL = ""

    @classmethod
    def from_source(cls, code: str) -> Parity:
        """Parse a parity field. A blank field is :attr:`ALL`."""
        try:
            return cls(code)
        except ValueError:
            raise ValueError(f"unknown parity code {code!r}") from None


@dataclass(frozen=True, slots=True)
class HouseNumberRange:
    """Inclusive house-number span on one PC6.

    ``from_number`` and ``to_number`` are the ``from`` / ``to`` columns.
    ``from`` is not a legal field name. ``street_id`` is ``0`` when the
    span is a postbus or an antwoordnummer and there is no street.
    """

    from_number: int
    to_number: int
    parity: Parity
    street_id: int
    city_id: int
    kind: SeriesKind

    def __post_init__(self) -> None:
        if (
            self.from_number < 0
            or self.to_number > MAX_HOUSE_NUMBER
            or self.from_number > self.to_number
        ):
            raise ValueError(
                f"invalid house-number span {self.from_number}..{self.to_number}"
            )
        if self.street_id < 0 or self.city_id < 0:
            raise ValueError("street_id and city_id must be >= 0")
        if self.parity is Parity.NO_NUMBER:
            if (self.from_number, self.to_number) != (0, 0):
                raise ValueError("a no-number range must be 0..0")
            return
        if self.parity is Parity.ALL:
            return
        if (self.to_number - self.from_number) % 2 != 0:
            raise ValueError(
                f"{self.parity.name} range {self.from_number}..{self.to_number} "
                "does not start and end on the same parity"
            )
        if self.parity is Parity.ODD and self.from_number % 2 == 0:
            raise ValueError(
                f"odd range starts on even house number {self.from_number}"
            )
        if self.parity is Parity.EVEN and self.from_number % 2 == 1:
            raise ValueError(
                f"even range starts on odd house number {self.from_number}"
            )

    def contains(self, house_number: int) -> bool:
        """Return whether ``house_number`` lies on this range.

        Odd, even and doorlopend ranges match every second number from
        ``from_number`` (``3``–``9`` odd contains 3, 5, 7 and 9).
        :attr:`Parity.ALL` matches every integer in the span. A
        no-number range contains only ``0``.
        """
        if house_number < self.from_number or house_number > self.to_number:
            return False
        if self.parity is Parity.ALL:
            return True
        return (house_number - self.from_number) % 2 == 0


@dataclass(frozen=True, slots=True)
class Street:
    """A street (openbare ruimte) from ``PCS_STR.dat``.

    Names are stored as published, including the ``" AB"`` suffix used for
    a numberless address (often a ligplaats). That suffix is not stripped:
    the same road can exist again without it, under a different id.
    """

    street_id: int
    name: str

    def __post_init__(self) -> None:
        if self.street_id <= 0:
            raise ValueError(f"street_id must be positive, got {self.street_id}")
        if not self.name:
            raise ValueError(f"street {self.street_id} has an empty name")


@dataclass(frozen=True, slots=True)
class City:
    """A city (woonplaats) from ``PCS_WPL.dat``.

    Names stay in the source casing, which is uppercase (``AMSTERDAM``,
    ``'S-GRAVENHAGE``). They are not title-cased.
    """

    city_id: int
    name: str

    def __post_init__(self) -> None:
        if self.city_id <= 0:
            raise ValueError(f"city_id must be positive, got {self.city_id}")
        if not self.name:
            raise ValueError(f"city {self.city_id} has an empty name")


# Chosen in-memory structures
# ---------------------------
# ranges_by_postcode: Mapping[PC6, tuple[HouseNumberRange, ...]]
#     Keyed by the normalised postcode ("1011 AA" -> "1011AA"). Validation
#     always starts from one postcode, and that postcode has only a few
#     ranges (an odd series, an even series, sometimes a second street).
#     A short tuple scanned linearly is smaller and faster than an interval
#     tree. Each range stores street and city *ids*, not names, so the
#     ~629k range rows do not repeat those strings.
#
# streets: Mapping[street_id, Street]
# cities:  Mapping[city_id, City]
#     One record per id, which is the id -> name index with the
#     name stored once on the record. Street id 0 is absent on purpose:
#     a postbus or antwoordnummer range has no street.
#
# HouseNumberRange, Street and City are frozen slotted dataclasses.
# InMemoryRepository copies its three maps into MappingProxyType and stores
# each postcode's ranges as a tuple, so a caller cannot append a row or
# replace a name after load.


@dataclass(frozen=True, slots=True, repr=False)
class InMemoryRepository:
    """Ready-to-query postcode, street and city tables.

    The three maps are read-only proxies. Each postcode maps to a tuple of
    ranges. ``ranges_for`` returns that tuple.
    """

    ranges_by_postcode: Mapping[str, tuple[HouseNumberRange, ...]]
    streets: Mapping[int, Street]
    cities: Mapping[int, City]

    def __post_init__(self) -> None:
        ranges = {
            postcode: tuple(rows) for postcode, rows in self.ranges_by_postcode.items()
        }
        object.__setattr__(self, "ranges_by_postcode", MappingProxyType(ranges))
        object.__setattr__(self, "streets", MappingProxyType(dict(self.streets)))
        object.__setattr__(self, "cities", MappingProxyType(dict(self.cities)))

    def __repr__(self) -> str:
        return (
            "InMemoryRepository("
            f"postcodes={len(self.ranges_by_postcode)}, "
            f"streets={len(self.streets)}, "
            f"cities={len(self.cities)})"
        )

    def ranges_for(self, postcode: str) -> tuple[HouseNumberRange, ...]:
        """Return the ranges on ``postcode``.

        ``postcode`` is normalised first. A well-formed postcode that is
        not in the table returns an empty tuple. The tuple is the one
        stored on the repository.

        Raises:
            ValueError: ``postcode`` is not a Dutch PC6.
        """
        return self.ranges_by_postcode.get(normalise_postcode(postcode), ())

    def matching_ranges(
        self, postcode: str, house_number: int
    ) -> tuple[HouseNumberRange, ...]:
        """Return every range on ``postcode`` that contains ``house_number``.

        A PC6 occasionally covers two streets, so more than one range can
        match. An unknown postcode returns an empty tuple. The result is a
        new tuple, not the stored series.
        """
        if house_number < 0:
            raise ValueError(f"house_number must be >= 0, got {house_number}")
        return tuple(
            range_
            for range_ in self.ranges_for(postcode)
            if range_.contains(house_number)
        )

    def street_name(self, street_id: int) -> str | None:
        """Return the street name, or ``None`` when the id is unknown.

        ``0`` is unknown: postbus and antwoordnummer ranges have no street.
        """
        street = self.streets.get(street_id)
        return None if street is None else street.name

    def city_name(self, city_id: int) -> str | None:
        """Return the city name, or ``None`` when the id is unknown."""
        city = self.cities.get(city_id)
        return None if city is None else city.name
