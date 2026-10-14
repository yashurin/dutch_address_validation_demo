"""Parsing the PCS files into the in-memory repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from address_validation import (
    DataFileError,
    InMemoryRepository,
    Parity,
    SeriesKind,
    create_repository,
)
from address_validation.loader import DataLoader

_STREETS = "\n".join(
    [
        "            1~Teststraat",
        "            2~Andere AB",
    ]
)
_CITIES = "  10~TESTSTAD\n"
_RANGES = "\n".join(
    [
        "1~1011~AA~1~5~O~1~10",
        "1~1011~AA~2~6~E~1~10",
        "2~1000~AA~1~10~~0~10",
        "3~1000~AB~4~4~~0~10",
        "4~1011~AB~0~0~G~2~10",
        "1~1011~AC~1~3~D~1~10",
        "1~1011~AC~2~4~D~1~10",
    ]
)


def _write(
    root: Path,
    *,
    streets: str = _STREETS + "\n",
    cities: str = _CITIES,
    ranges: str = _RANGES + "\n",
) -> Path:
    (root / "PCS_STR.dat").write_text(streets, encoding="utf-8")
    (root / "PCS_WPL.dat").write_text(cities, encoding="utf-8")
    (root / "PCS_HNR.dat").write_text(ranges, encoding="utf-8")
    return root


def test_synthetic_files(tmp_path: Path) -> None:
    repo = DataLoader(_write(tmp_path)).load()

    assert repo.street_name(1) == "Teststraat"
    assert repo.street_name(2) == "Andere AB"
    assert repo.street_name(0) is None
    assert repo.city_name(10) == "TESTSTAD"

    odd, even = repo.ranges_for("1011 aa")
    assert odd.parity is Parity.ODD
    assert odd.kind is SeriesKind.STREET
    assert even.from_number == 2
    assert [range_.kind for range_ in repo.matching_ranges("1011AA", 4)] == [
        SeriesKind.STREET
    ]
    assert repo.matching_ranges("1011AA", 4)[0].parity is Parity.EVEN
    assert repo.matching_ranges("1011AA", 7) == []

    box = repo.matching_ranges("1000 AA", 10)[0]
    assert box.kind is SeriesKind.PO_BOX
    assert box.street_id == 0
    assert repo.matching_ranges("1000AA", 11) == []

    reply = repo.ranges_for("1000AB")[0]
    assert reply.kind is SeriesKind.REPLY_NUMBER
    assert reply.contains(4)
    assert not reply.contains(5)

    bare = repo.ranges_for("1011AB")[0]
    assert bare.kind is SeriesKind.NO_HOUSE_NUMBER
    assert repo.street_name(bare.street_id) == "Andere AB"
    assert repo.matching_ranges("1011AB", 0) == [bare]

    low, high = repo.ranges_for("1011AC")
    assert low.parity is Parity.DOORLOPEND
    assert low.contains(1)
    assert not low.contains(2)
    assert high.contains(2)
    assert high.contains(4)

    assert repo.ranges_for("9999ZZ") == []
    assert "postcodes=5" in repr(repo)


def test_unknown_street_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, ranges="1~1011~AA~1~5~O~99~10\n")
    with pytest.raises(DataFileError, match="street id 99"):
        DataLoader(root).load()


def test_postbus_with_a_street_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, ranges="2~1000~AA~1~10~O~1~10\n")
    with pytest.raises(DataFileError):
        DataLoader(root).load()


def test_short_row_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, ranges="1~1011~AA~1~5~O~1\n")
    with pytest.raises(DataFileError, match="expected 8 fields"):
        DataLoader(root).load()


def test_duplicate_street_id_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, streets="1~A\n1~B\n")
    with pytest.raises(DataFileError, match="duplicate street id 1"):
        DataLoader(root).load()


def test_missing_file(tmp_path: Path) -> None:
    root = _write(tmp_path)
    (root / "PCS_WPL.dat").unlink()
    with pytest.raises(FileNotFoundError):
        create_repository(root)


def test_loaded_repository_contains_smallepad(
    repository: InMemoryRepository,
) -> None:
    ranges = repository.ranges_for("3811 MG")
    assert [(r.from_number, r.to_number, r.parity) for r in ranges] == [
        (2, 90, Parity.EVEN),
        (3, 23, Parity.ODD),
    ]
    assert repository.street_name(ranges[0].street_id) == "Smallepad"
    assert repository.city_name(ranges[0].city_id) == "AMERSFOORT"
    assert len(repository.streets) == 138_262
    assert len(repository.cities) == 2_458
    assert len(repository.ranges_by_postcode) == 472_488
    assert (
        sum(len(ranges) for ranges in repository.ranges_by_postcode.values())
        == 629_336
    )
