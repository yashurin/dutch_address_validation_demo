"""Lookup and validation against the loaded repository.

Cases that the PCS files do not contain use a tiny in-memory repository
built in the test, so the session load stays shared and the extra cases
stay cheap.
"""

from __future__ import annotations

import pytest

from address_validation import (
    AddressService,
    City,
    HouseNumberRange,
    InMemoryRepository,
    InvalidAddress,
    LookupReason,
    LookupResult,
    Parity,
    SeriesKind,
    Street,
)

_SMALLEPAD = ["Smallepad 30E", "3811 MG  AMERSFOORT"]
_SMALLEPAD_BARE = ["Smallepad 30", "3811 MG  AMERSFOORT"]


def _found(result: LookupResult) -> list[str]:
    assert result.reason is None
    return list(result.lines)


def _missing(result: LookupResult) -> None:
    assert result.reason is LookupReason.NOT_FOUND
    assert result.lines == ()


def test_known_address_smallepad(service: AddressService) -> None:
    assert _found(service.lookup_address("3811 MG", 30, "E")) == _SMALLEPAD
    assert _found(service.lookup_address("3811mg", "30", "e")) == _SMALLEPAD
    city_line = _SMALLEPAD[1]
    assert city_line.split("  ") == ["3811 MG", "AMERSFOORT"]


def test_missing_extension(service: AddressService) -> None:
    assert _found(service.lookup_address("3811 MG", 30)) == _SMALLEPAD_BARE
    assert _found(service.lookup_address("3811 MG", 30, "")) == _SMALLEPAD_BARE
    assert _found(service.lookup_address("3811 MG", 30, "-")) == _SMALLEPAD_BARE
    assert service.validate("Smallepad", 30, None, "3811 MG", "AMERSFOORT")
    assert service.validate("smallepad", "30", "", "3811mg", "amersfoort")
    assert service.validate("Smallepad", 30, "-", "3811 MG", "Amersfoort")


@pytest.mark.parametrize(
    ("house_number", "expected"),
    [
        (30, _SMALLEPAD_BARE),
        (4, ["Smallepad 4", "3811 MG  AMERSFOORT"]),
        (90, ["Smallepad 90", "3811 MG  AMERSFOORT"]),
        (23, ["Smallepad 23", "3811 MG  AMERSFOORT"]),
        (31, []),
        (1, []),
        (92, []),
    ],
)
def test_odd_and_even_ranges(
    service: AddressService,
    house_number: int,
    expected: list[str],
) -> None:
    # 3811 MG stores evens 2–90 and odds 3–23, both on Smallepad.
    result = service.lookup_address("3811 MG", house_number)
    if expected:
        assert _found(result) == expected
    else:
        _missing(result)


@pytest.mark.parametrize(
    "postcode",
    ["", "   ", "3811", "3811 M", "nope", "0000 AA", None],
)
def test_invalid_postcode(service: AddressService, postcode: str | None) -> None:
    with pytest.raises(InvalidAddress):
        service.lookup_address(postcode, 30, "E")  # type: ignore[arg-type]


def test_unknown_postcode_is_a_miss(service: AddressService) -> None:
    _missing(service.lookup_address("9999 ZZ", 1))
    assert not service.validate("Smallepad", 1, None, "9999 ZZ", "AMERSFOORT")


@pytest.mark.parametrize("house_number", ["", "   ", "nope", True])
def test_empty_or_unreadable_house_number(
    service: AddressService,
    house_number: str,
) -> None:
    with pytest.raises(InvalidAddress):
        service.lookup_address("3811 MG", house_number)  # type: ignore[arg-type]


def test_validation_succeeds_for_the_known_address(service: AddressService) -> None:
    assert service.validate("Smallepad", 30, "E", "3811 MG", "AMERSFOORT")
    assert service.validate("smallepad", "30e", None, "3811 mg", "amersfoort")
    found = service.lookup_address("3811 MG", 30, "E")
    assert service.validate_lines(found.lines)
    assert service.validate_lines(service.lookup_address("3811 MG", 30).lines)


@pytest.mark.parametrize(
    ("street", "house_number", "extension", "postcode", "city"),
    [
        ("Smallepad", 31, None, "3811 MG", "AMERSFOORT"),
        ("Smallepad", 1, None, "3811 MG", "AMERSFOORT"),
        ("Andere Straat", 30, None, "3811 MG", "AMERSFOORT"),
        ("Smallepad", 30, None, "3811 MG", "UTRECHT"),
    ],
)
def test_validation_misses(
    service: AddressService,
    street: str,
    house_number: int | str,
    extension: str | None,
    postcode: str,
    city: str,
) -> None:
    assert not service.validate(street, house_number, extension, postcode, city)


@pytest.mark.parametrize(
    ("street", "house_number", "extension", "postcode", "city"),
    [
        ("Smallepad", 30, "E", "3811", "AMERSFOORT"),
        ("Smallepad", 30, "E", "", "AMERSFOORT"),
        ("Smallepad", 30, "E", "nope", "AMERSFOORT"),
        ("Smallepad", 30, "no spaces", "3811 MG", "AMERSFOORT"),
        ("Smallepad", "30E", "B", "3811 MG", "AMERSFOORT"),
        ("", 30, None, "3811 MG", "AMERSFOORT"),
        ("Smallepad", 30, None, "3811 MG", ""),
        ("Smallepad", "", None, "3811 MG", "AMERSFOORT"),
    ],
)
def test_validation_rejects_malformed_input(
    service: AddressService,
    street: str,
    house_number: int | str,
    extension: str | None,
    postcode: str,
    city: str,
) -> None:
    with pytest.raises(InvalidAddress):
        service.validate(street, house_number, extension, postcode, city)


@pytest.mark.parametrize(
    "lines",
    [
        ["Smallepad 30E", "3811 MG  AMERSFOORT"],
        ["smallepad 30 e", "3811 mg amersfoort"],
        ["", "  Smallepad 30 ", "3811 MG AMERSFOORT"],
        ["Smallepad 30", "3811 MG  AMERSFOORT"],
    ],
)
def test_validate_lines_accepts_two_line_addresses(
    service: AddressService,
    lines: list[str],
) -> None:
    assert service.validate_lines(lines)


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [""],
        ["   ", ""],
        ["Smallepad 30E"],
        ["Smallepad 30E", "3811 MG  AMERSFOORT", "extra"],
        ["Smallepad 30E", "not a postcode"],
        ["Smallepad 30E", "3811 MG"],
        ["Smallepad 30E", "0000 AA  AMERSFOORT"],
        ["", ""],
    ],
)
def test_validate_lines_rejects_malformed_addresses(
    service: AddressService,
    lines: list[str],
) -> None:
    with pytest.raises(InvalidAddress):
        service.validate_lines(lines)


@pytest.mark.parametrize(
    "lines",
    [
        ["Smallepad 31", "3811 MG  AMERSFOORT"],
        ["Andere Straat 30", "3811 MG  AMERSFOORT"],
        ["Smallepad 30E", "3811 MG  UTRECHT"],
    ],
)
def test_validate_lines_misses(service: AddressService, lines: list[str]) -> None:
    assert not service.validate_lines(lines)


def test_extension_round_trip(service: AddressService) -> None:
    single = service.lookup_address("3811 MG", "30a")
    assert single.lines[0] == "Smallepad 30A"
    assert service.validate_lines(single.lines)
    longer = service.lookup_address("3811 MG", 30, "BIS")
    assert longer.lines[0] == "Smallepad 30-bis"
    assert service.validate_lines(longer.lines)
    assert service.validate("Smallepad", 30, "-a", "3811 MG", "AMERSFOORT")
    with pytest.raises(InvalidAddress):
        service.lookup_address("3811 MG", "30A", "B")


def test_postbus_reply_and_numberless(service: AddressService) -> None:
    box = service.lookup_address("1000 AA", 25)
    assert _found(box) == ["Postbus 25", "1000 AA  AMSTERDAM"]
    assert service.validate("postbus", 25, None, "1000AA", "Amsterdam")
    _missing(service.lookup_address("1000 AA", 50))

    reply = service.lookup_address("1000 pa", "5")
    assert _found(reply) == ["Antwoordnummer 5", "1000 PA  AMSTERDAM"]
    assert service.validate_lines(reply.lines)

    bare = service.lookup_address("1013 LC", 0)
    assert _found(bare) == ["Zoutkeetsgracht AB", "1013 LC  AMSTERDAM"]
    assert service.validate_lines(bare.lines)
    numbered = service.lookup_address("1013LC", 1)
    assert numbered.lines[0] == "Zoutkeetsgracht 1"
    assert not service.validate(
        "Zoutkeetsgracht AB",
        1,
        None,
        "1013 LC",
        "AMSTERDAM",
    )


def test_apostrophe_and_doorlopend(service: AddressService) -> None:
    gravel = service.lookup_address("1011 KM", 1)
    assert _found(gravel) == ["'s Gravelandseveer 1", "1011 KM  AMSTERDAM"]
    assert service.validate_lines(["\u2019s  Gravelandseveer 1", "1011 km AMSTERDAM"])
    assert not service.validate(
        "'s Gravelandseveer",
        8,
        None,
        "1011 KM",
        "AMSTERDAM",
    )
    # Doorlopend series are stored as one odd row and one even row.
    assert _found(service.lookup_address("1011 MR", 2)) == [
        "Koerierstersplein 2",
        "1011 MR  AMSTERDAM",
    ]
    _missing(service.lookup_address("1011 MR", 19))


@pytest.fixture
def ambiguous_service() -> AddressService:
    """Two streets contain the same odd numbers. The files do not."""
    return AddressService(
        InMemoryRepository(
            ranges_by_postcode={
                "2000AB": [
                    HouseNumberRange(1, 9, Parity.ODD, 1, 1000, SeriesKind.STREET),
                    HouseNumberRange(1, 9, Parity.ODD, 2, 1000, SeriesKind.STREET),
                ],
            },
            streets={
                1: Street(1, "De Ruyterkade Steigers"),
                2: Street(2, "Andere Straat"),
            },
            cities={1000: City(1000, "AMSTERDAM")},
        )
    )


def test_ambiguous_house_number_is_not_guessed(
    ambiguous_service: AddressService,
) -> None:
    ambiguous = ambiguous_service.lookup_address("2000 AB", 1)
    assert ambiguous.lines == ()
    assert ambiguous.reason is LookupReason.AMBIGUOUS
    assert ambiguous_service.validate("Andere Straat", 1, None, "2000AB", "AMSTERDAM")
    assert ambiguous_service.validate(
        "De Ruyterkade Steigers",
        1,
        None,
        "2000 AB",
        "AMSTERDAM",
    )
