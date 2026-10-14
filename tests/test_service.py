"""AddressService lookup, validation, and normalisation."""

from __future__ import annotations

import unittest
from pathlib import Path

from address_validation import (
    AddressService,
    City,
    HouseNumberRange,
    InMemoryRepository,
    Parity,
    SeriesKind,
    Street,
    format_postcode,
    normalise_extension,
    normalise_name,
)
from address_validation.normalise import resolve_house_number
from address_validation.service import parse_address_lines

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _service() -> AddressService:
    ranges = {
        "1011AA": [
            HouseNumberRange(3, 9, Parity.ODD, 1, 1000, SeriesKind.STREET),
            HouseNumberRange(6, 10, Parity.EVEN, 1, 1000, SeriesKind.STREET),
        ],
        "1011KM": [
            HouseNumberRange(1, 5, Parity.ODD, 4, 1000, SeriesKind.STREET),
            HouseNumberRange(2, 6, Parity.EVEN, 4, 1000, SeriesKind.STREET),
        ],
        "1000AA": [
            HouseNumberRange(1, 49, Parity.ALL, 0, 1000, SeriesKind.PO_BOX),
        ],
        "1000PA": [
            HouseNumberRange(5, 5, Parity.ALL, 0, 1000, SeriesKind.REPLY_NUMBER),
        ],
        "1013LC": [
            HouseNumberRange(0, 0, Parity.NO_NUMBER, 2, 1000, SeriesKind.NO_HOUSE_NUMBER),
            HouseNumberRange(1, 11, Parity.ODD, 3, 1000, SeriesKind.STREET),
        ],
        "2000AB": [
            HouseNumberRange(1, 9, Parity.ODD, 1, 1000, SeriesKind.STREET),
            HouseNumberRange(1, 9, Parity.ODD, 5, 1000, SeriesKind.STREET),
        ],
    }
    streets = {
        1: Street(1, "De Ruyterkade Steigers"),
        2: Street(2, "Zoutkeetsgracht AB"),
        3: Street(3, "Zoutkeetsgracht"),
        4: Street(4, "'s Gravelandseveer"),
        5: Street(5, "Andere Straat"),
    }
    cities = {1000: City(1000, "AMSTERDAM")}
    return AddressService(
        InMemoryRepository(
            ranges_by_postcode=ranges,
            streets=streets,
            cities=cities,
        )
    )


class NormaliseTests(unittest.TestCase):
    def test_postcode_display_form(self) -> None:
        self.assertEqual(format_postcode("1011aa"), "1011 AA")
        self.assertEqual(AddressService.format_postcode("  1011  AA "), "1011 AA")
        self.assertEqual(AddressService.normalise_postcode("1011 aa"), "1011AA")

    def test_name_folding(self) -> None:
        self.assertEqual(normalise_name("  De   Ruyterkade "), "de ruyterkade")
        self.assertEqual(
            normalise_name("\u2019s Gravelandseveer"),
            normalise_name("'s Gravelandseveer"),
        )

    def test_extension_folding(self) -> None:
        self.assertEqual(normalise_extension("-a"), "A")
        self.assertEqual(normalise_extension("BIS"), "bis")
        self.assertIsNone(normalise_extension(None))
        self.assertIsNone(normalise_extension(" - "))
        with self.assertRaises(ValueError):
            normalise_extension("no spaces")
        self.assertEqual(resolve_house_number("12-A"), (12, "A"))
        self.assertEqual(resolve_house_number("12a", "A"), (12, "A"))
        self.assertEqual(resolve_house_number(7, None), (7, None))
        with self.assertRaises(ValueError):
            resolve_house_number("12a", "B")


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _service()

    def test_lookup_formats_two_spaces_before_the_city(self) -> None:
        lines = self.service.lookup_address("1011 aa", 7)
        self.assertEqual(
            lines,
            ["De Ruyterkade Steigers 7", "1011 AA  AMSTERDAM"],
        )
        self.assertEqual(lines[1].split("  "), ["1011 AA", "AMSTERDAM"])
        self.assertTrue(self.service.validate_lines(lines))

    def test_parity_and_postcode_spelling(self) -> None:
        service = self.service
        self.assertEqual(service.lookup_address("1011AA", 4), [])
        self.assertEqual(service.lookup_address("1011 AA", 2), [])
        self.assertTrue(
            service.validate(
                "de ruyterkade steigers",
                "08",
                None,
                "1011aa",
                "amsterdam",
            )
        )
        self.assertFalse(
            service.validate(
                "De Ruyterkade Steigers",
                4,
                None,
                "1011 AA",
                "AMSTERDAM",
            )
        )
        self.assertFalse(
            service.validate(
                "Andere Straat",
                8,
                None,
                "1011 AA",
                "AMSTERDAM",
            )
        )

    def test_extension_is_optional_and_round_trips(self) -> None:
        service = self.service
        lines = service.lookup_address("1011 AA", "7a")
        self.assertEqual(lines[0], "De Ruyterkade Steigers 7A")
        self.assertTrue(service.validate_lines(lines))
        bis = service.lookup_address("1011 AA", 8, "BIS")
        self.assertEqual(bis[0], "De Ruyterkade Steigers 8-bis")
        self.assertTrue(service.validate_lines(bis))
        self.assertTrue(
            service.validate(
                "De Ruyterkade Steigers",
                7,
                "-a",
                "1011 AA",
                "AMSTERDAM",
            )
        )
        self.assertEqual(service.lookup_address("1011 AA", "7A", "B"), [])
        self.assertFalse(
            service.validate(
                "De Ruyterkade Steigers",
                7,
                "no spaces",
                "1011 AA",
                "AMSTERDAM",
            )
        )

    def test_postbus_antwoordnummer_and_numberless(self) -> None:
        service = self.service
        box = service.lookup_address("1000 AA", 25)
        self.assertEqual(box, ["Postbus 25", "1000 AA  AMSTERDAM"])
        self.assertTrue(
            service.validate("postbus", 25, None, "1000AA", "Amsterdam")
        )
        self.assertEqual(service.lookup_address("1000 AA", 50), [])

        reply = service.lookup_address("1000 pa", "5")
        self.assertEqual(reply, ["Antwoordnummer 5", "1000 PA  AMSTERDAM"])
        self.assertTrue(service.validate_lines(reply))

        bare = service.lookup_address("1013 LC", 0)
        self.assertEqual(bare, ["Zoutkeetsgracht AB", "1013 LC  AMSTERDAM"])
        self.assertTrue(service.validate_lines(bare))
        numbered = service.lookup_address("1013LC", 1)
        self.assertEqual(numbered[0], "Zoutkeetsgracht 1")
        self.assertFalse(
            service.validate(
                "Zoutkeetsgracht AB",
                1,
                None,
                "1013 LC",
                "AMSTERDAM",
            )
        )

    def test_ambiguous_house_number_is_not_guessed(self) -> None:
        service = self.service
        self.assertEqual(service.lookup_address("2000 AB", 1), [])
        self.assertTrue(
            service.validate("Andere Straat", 1, None, "2000AB", "AMSTERDAM")
        )
        self.assertTrue(
            service.validate(
                "De Ruyterkade Steigers",
                1,
                None,
                "2000 AB",
                "AMSTERDAM",
            )
        )

    def test_validate_lines_accepts_spacing_variants(self) -> None:
        service = self.service
        self.assertTrue(
            service.validate_lines(
                [
                    "",
                    "  de   ruyterkade steigers 7 A ",
                    "1011 AA AMSTERDAM",
                ]
            )
        )
        self.assertTrue(
            service.validate_lines(
                ["'s Gravelandseveer 1", "1011 km  amsterdam"]
            )
        )
        self.assertTrue(
            service.validate(
                "\u2019s Gravelandseveer",
                1,
                None,
                "1011 KM",
                "Amsterdam",
            )
        )
        self.assertFalse(service.validate_lines(["only one line"]))
        self.assertFalse(
            service.validate_lines(
                [
                    "De Ruyterkade Steigers 7",
                    "1011 AA  AMSTERDAM",
                    "extra",
                ]
            )
        )
        self.assertIsNone(parse_address_lines("1011 AA  AMSTERDAM"))
        parsed = parse_address_lines(["Laan 1945 10 bis", "1011 AA  AMSTERDAM"])
        self.assertEqual(parsed[:3], ("Laan 1945", 10, "bis"))


@unittest.skipUnless((DATA_DIR / "PCS_HNR.dat").is_file(), "PCS data files not present")
class RealServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = AddressService.load(DATA_DIR)

    def test_known_street_parity_and_apostrophe(self) -> None:
        service = self.service
        lines = service.lookup_address("1011 AA", 7)
        self.assertEqual(
            lines,
            ["De Ruyterkade Steigers 7", "1011 AA  AMSTERDAM"],
        )
        self.assertTrue(service.validate_lines(lines))
        self.assertEqual(service.lookup_address("1011aa", 4), [])
        self.assertTrue(
            service.validate(
                "De Ruyterkade Steigers",
                6,
                "A",
                "1011 aa",
                "amsterdam",
            )
        )

        gravel = service.lookup_address("1011 KM", 1)
        self.assertEqual(
            gravel,
            ["'s Gravelandseveer 1", "1011 KM  AMSTERDAM"],
        )
        self.assertTrue(
            service.validate_lines(
                ["\u2019s  Gravelandseveer 1", "1011 km AMSTERDAM"]
            )
        )
        self.assertFalse(
            service.validate(
                "'s Gravelandseveer",
                8,
                None,
                "1011 KM",
                "AMSTERDAM",
            )
        )
        # 1011 MR is a doorlopend street, stored as one odd row and one even row.
        self.assertEqual(
            service.lookup_address("1011 MR", 2),
            ["Koerierstersplein 2", "1011 MR  AMSTERDAM"],
        )
        self.assertEqual(service.lookup_address("1011 MR", 19), [])

    def test_postbus_reply_and_numberless_from_the_files(self) -> None:
        service = self.service
        self.assertEqual(
            service.lookup_address("1000 AA", 25),
            ["Postbus 25", "1000 AA  AMSTERDAM"],
        )
        self.assertEqual(
            service.lookup_address("1000 PA", 5),
            ["Antwoordnummer 5", "1000 PA  AMSTERDAM"],
        )
        self.assertEqual(
            service.lookup_address("1013 LC", 0),
            ["Zoutkeetsgracht AB", "1013 LC  AMSTERDAM"],
        )
        self.assertEqual(
            service.lookup_address("1013 LC", 1),
            ["Zoutkeetsgracht 1", "1013 LC  AMSTERDAM"],
        )
        self.assertTrue(
            service.validate_lines(
                ["Zoutkeetsgracht AB", "1013 LC  AMSTERDAM"]
            )
        )
