"""House-number parity, independent of the PCS files."""

from __future__ import annotations

import pytest

from address_validation import HouseNumberRange, Parity, SeriesKind


def test_odd_even_doorlopend_and_all() -> None:
    odd = HouseNumberRange(3, 9, Parity.ODD, 1, 10, SeriesKind.STREET)
    even = HouseNumberRange(2, 6, Parity.EVEN, 1, 10, SeriesKind.STREET)
    running = HouseNumberRange(1, 17, Parity.DOORLOPEND, 1, 10, SeriesKind.STREET)
    boxes = HouseNumberRange(1, 49, Parity.ALL, 0, 10, SeriesKind.PO_BOX)
    none = HouseNumberRange(0, 0, Parity.NO_NUMBER, 2, 10, SeriesKind.NO_HOUSE_NUMBER)

    assert [n for n in range(1, 12) if odd.contains(n)] == [3, 5, 7, 9]
    assert [n for n in range(1, 8) if even.contains(n)] == [2, 4, 6]
    assert running.contains(1)
    assert running.contains(17)
    assert not running.contains(2)
    assert all(boxes.contains(n) for n in range(1, 50))
    assert not boxes.contains(0)
    assert not boxes.contains(50)
    assert none.contains(0)
    assert not none.contains(1)


@pytest.mark.parametrize(
    ("start", "end", "parity", "kind"),
    [
        (2, 8, Parity.ODD, SeriesKind.STREET),
        (1, 4, Parity.ODD, SeriesKind.STREET),
        (1, 1, Parity.NO_NUMBER, SeriesKind.NO_HOUSE_NUMBER),
    ],
)
def test_rejects_a_span_that_breaks_its_parity(
    start: int,
    end: int,
    parity: Parity,
    kind: SeriesKind,
) -> None:
    with pytest.raises(ValueError):
        HouseNumberRange(start, end, parity, 1, 10, kind)


def test_blank_source_parity_is_all() -> None:
    assert Parity.from_source("") is Parity.ALL
    assert Parity.from_source("O") is Parity.ODD
    with pytest.raises(ValueError):
        Parity.from_source("A")
