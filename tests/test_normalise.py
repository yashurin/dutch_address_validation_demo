"""Postcode, name, and extension folding. No reference data."""

from __future__ import annotations

import pytest

from address_validation import (
    AddressService,
    format_postcode,
    normalise_extension,
    normalise_name,
    normalise_postcode,
)
from address_validation.normalise import resolve_house_number
from address_validation.service import parse_address_lines


def test_postcode_folds_spaces_and_case() -> None:
    assert normalise_postcode("1011 aa") == "1011AA"
    assert normalise_postcode("  1011  AA ") == "1011AA"
    assert normalise_postcode("1011AA") == "1011AA"
    assert format_postcode("1011aa") == "1011 AA"
    assert AddressService.format_postcode("  1011  AA ") == "1011 AA"
    assert AddressService.normalise_postcode("1011 aa") == "1011AA"


@pytest.mark.parametrize("value", ["1011", "1011A", "0011AA", "10111AA", ""])
def test_postcode_rejects_a_partial_code(value: str) -> None:
    with pytest.raises(ValueError):
        normalise_postcode(value)


def test_name_folding() -> None:
    assert normalise_name("  De   Ruyterkade ") == "de ruyterkade"
    assert normalise_name("\u2019s Gravelandseveer") == normalise_name(
        "'s Gravelandseveer"
    )


def test_extension_folding() -> None:
    assert normalise_extension("-a") == "A"
    assert normalise_extension("BIS") == "bis"
    assert normalise_extension(None) is None
    assert normalise_extension(" - ") is None
    with pytest.raises(ValueError):
        normalise_extension("no spaces")


def test_house_number_and_extension_agree() -> None:
    assert resolve_house_number("12-A") == (12, "A")
    assert resolve_house_number("12a", "A") == (12, "A")
    assert resolve_house_number(7, None) == (7, None)
    with pytest.raises(ValueError):
        resolve_house_number("12a", "B")


def test_last_number_on_the_street_line_is_the_house_number() -> None:
    parsed = parse_address_lines(["Laan 1945 10 bis", "3811 MG  AMERSFOORT"])
    assert parsed is not None
    assert parsed[:3] == ("Laan 1945", 10, "bis")
    assert parse_address_lines("3811 MG  AMERSFOORT") is None
