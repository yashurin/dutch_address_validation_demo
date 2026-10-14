"""Load ``PCS_HNR.dat``, ``PCS_STR.dat`` and ``PCS_WPL.dat``.

The three files are tilde-separated and space-padded, with CRLF line
endings. Text mode collapses the line ending; each field is then stripped.

``PCS_STR.dat`` — ``street_id ~ name``
``PCS_WPL.dat`` — ``city_id ~ name``
``PCS_HNR.dat`` — eight fields:

    kind ~ pc4 ~ letters ~ from ~ to ~ parity ~ street_id ~ city_id

``kind`` is 1 street, 2 postbus, 3 antwoordnummer, 4 no house number.
``parity`` is ``O`` odd, ``E`` even, ``D`` doorlopend, ``G`` no house
number, or blank (every integer in the span). ``street_id`` is ``0``
when the row has no street. See :class:`address_validation.models.Parity`
for how a span is matched.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from address_validation.models import (
    City,
    HouseNumberRange,
    InMemoryRepository,
    Parity,
    SeriesKind,
    Street,
)
from address_validation.postcode import normalise_postcode

HOUSE_NUMBER_FILE = "PCS_HNR.dat"
STREET_FILE = "PCS_STR.dat"
CITY_FILE = "PCS_WPL.dat"

_HOUSE_NUMBER_FIELDS = 8


class DataFileError(ValueError):
    """A PCS file has a row that this loader cannot accept."""

    def __init__(self, path: Path, line_number: int, message: str) -> None:
        self.path = path
        self.line_number = line_number
        super().__init__(f"{path.name}:{line_number}: {message}")


class DataLoader:
    """Parse a directory of PCS files into an :class:`InMemoryRepository`.

    The directory must contain :data:`HOUSE_NUMBER_FILE`,
    :data:`STREET_FILE` and :data:`CITY_FILE`. Streets and cities are
    loaded first, and every range id is checked against those tables.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    def load(self) -> InMemoryRepository:
        """Read the three files and return the in-memory repository."""
        cities = self._load_cities(self._existing(CITY_FILE))
        streets = self._load_streets(self._existing(STREET_FILE))
        ranges = self._load_ranges(
            self._existing(HOUSE_NUMBER_FILE),
            streets,
            cities,
        )
        return InMemoryRepository(
            ranges_by_postcode=ranges,
            streets=streets,
            cities=cities,
        )

    def _existing(self, name: str) -> Path:
        path = self.data_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _load_streets(self, path: Path) -> dict[int, Street]:
        streets: dict[int, Street] = {}
        for line_number, line in _lines(path):
            street_id_text, separator, name = line.partition("~")
            if separator == "":
                raise DataFileError(path, line_number, "expected street_id~name")
            street_id = _parse_int(path, line_number, "street_id", street_id_text.strip())
            try:
                street = Street(street_id, name.strip())
            except ValueError as exc:
                raise DataFileError(path, line_number, str(exc)) from exc
            if street_id in streets:
                raise DataFileError(path, line_number, f"duplicate street id {street_id}")
            streets[street_id] = street
        return streets

    def _load_cities(self, path: Path) -> dict[int, City]:
        cities: dict[int, City] = {}
        for line_number, line in _lines(path):
            city_id_text, separator, name = line.partition("~")
            if separator == "":
                raise DataFileError(path, line_number, "expected city_id~name")
            city_id = _parse_int(path, line_number, "city_id", city_id_text.strip())
            try:
                city = City(city_id, name.strip())
            except ValueError as exc:
                raise DataFileError(path, line_number, str(exc)) from exc
            if city_id in cities:
                raise DataFileError(path, line_number, f"duplicate city id {city_id}")
            cities[city_id] = city
        return cities

    def _load_ranges(
        self,
        path: Path,
        streets: dict[int, Street],
        cities: dict[int, City],
    ) -> dict[str, list[HouseNumberRange]]:
        # Built as a defaultdict so each PC6 grows one list, then copied to
        # a plain dict. A defaultdict would insert an empty list on any
        # accidental lookup of an unknown postcode.
        grouped: dict[str, list[HouseNumberRange]] = defaultdict(list)
        for line_number, line in _lines(path):
            fields = [field.strip() for field in line.split("~")]
            if len(fields) != _HOUSE_NUMBER_FIELDS:
                raise DataFileError(
                    path,
                    line_number,
                    f"expected {_HOUSE_NUMBER_FIELDS} fields, got {len(fields)}",
                )
            (
                kind_text,
                pc4,
                letters,
                from_text,
                to_text,
                parity_text,
                street_text,
                city_text,
            ) = fields
            try:
                postcode = normalise_postcode(pc4 + letters)
                kind = SeriesKind(int(kind_text))
                parity = Parity.from_source(parity_text)
            except ValueError as exc:
                raise DataFileError(path, line_number, str(exc)) from exc
            from_number = _parse_int(path, line_number, "from", from_text)
            to_number = _parse_int(path, line_number, "to", to_text)
            street_id = _parse_int(path, line_number, "street_id", street_text)
            city_id = _parse_int(path, line_number, "city_id", city_text)
            try:
                _check_series(kind, parity, street_id)
                if city_id not in cities:
                    raise ValueError(f"city id {city_id} is not in {CITY_FILE}")
                if street_id != 0 and street_id not in streets:
                    raise ValueError(f"street id {street_id} is not in {STREET_FILE}")
                range_ = HouseNumberRange(
                    from_number=from_number,
                    to_number=to_number,
                    parity=parity,
                    street_id=street_id,
                    city_id=city_id,
                    kind=kind,
                )
            except ValueError as exc:
                raise DataFileError(path, line_number, f"{postcode}: {exc}") from exc
            grouped[postcode].append(range_)
        return dict(grouped)


def create_repository(data_dir: str | Path = "data") -> InMemoryRepository:
    """Factory: load ``data_dir`` and return a ready-to-query repository.

    ``data_dir`` defaults to ``./data`` and must contain the three PCS
    files. Postcodes are normalised while the house-number file is read.
    """
    return DataLoader(data_dir).load()


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    """Yield ``(line_number, line_without_ending)`` for every content row.

    Rows are streamed. The house-number file is about 21 MB and 629k
    lines, so the loader never holds a second copy of the raw text.
    """
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.rstrip("\r\n")
            if text.strip() == "":
                continue
            yield line_number, text


def _parse_int(path: Path, line_number: int, field_name: str, text: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise DataFileError(
            path, line_number, f"invalid {field_name} {text!r}"
        ) from exc


def _check_series(kind: SeriesKind, parity: Parity, street_id: int) -> None:
    """Enforce the kind / parity / street combination this extract uses.

    These relations hold on every row of the published files. Rejecting a
    break here catches a shifted column instead of loading a silent mix of
    postbus ranges and street ranges.
    """
    if kind in (SeriesKind.PO_BOX, SeriesKind.REPLY_NUMBER):
        if parity is not Parity.ALL or street_id != 0:
            raise ValueError(
                f"{kind.name} rows must have a blank parity and street id 0"
            )
        return
    if kind is SeriesKind.NO_HOUSE_NUMBER:
        if parity is not Parity.NO_NUMBER or street_id == 0:
            raise ValueError(
                f"{kind.name} rows must have parity G and a real street id"
            )
        return
    if parity not in (Parity.ODD, Parity.EVEN, Parity.DOORLOPEND) or street_id == 0:
        raise ValueError(
            f"{kind.name} rows must have parity O, E or D and a real street id"
        )
