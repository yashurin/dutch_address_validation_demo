"""Loader, postcode and range-matching tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from address_validation import (
    DataFileError,
    HouseNumberRange,
    Parity,
    SeriesKind,
    create_repository,
    normalise_postcode,
)
from address_validation.loader import DataLoader

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

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


class PostcodeTests(unittest.TestCase):
    def test_normalise_removes_spaces_and_uppercases(self) -> None:
        self.assertEqual(normalise_postcode("1011 aa"), "1011AA")
        self.assertEqual(normalise_postcode("  1011  AA "), "1011AA")
        self.assertEqual(normalise_postcode("1011AA"), "1011AA")

    def test_normalise_rejects_a_partial_code(self) -> None:
        for value in ("1011", "1011A", "0011AA", "10111AA", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalise_postcode(value)


class RangeModelTests(unittest.TestCase):
    def test_odd_even_doorlopend_and_all(self) -> None:
        odd = HouseNumberRange(3, 9, Parity.ODD, 1, 10, SeriesKind.STREET)
        even = HouseNumberRange(2, 6, Parity.EVEN, 1, 10, SeriesKind.STREET)
        running = HouseNumberRange(1, 17, Parity.DOORLOPEND, 1, 10, SeriesKind.STREET)
        boxes = HouseNumberRange(1, 49, Parity.ALL, 0, 10, SeriesKind.PO_BOX)
        none = HouseNumberRange(0, 0, Parity.NO_NUMBER, 2, 10, SeriesKind.NO_HOUSE_NUMBER)

        self.assertEqual([n for n in range(1, 12) if odd.contains(n)], [3, 5, 7, 9])
        self.assertEqual([n for n in range(1, 8) if even.contains(n)], [2, 4, 6])
        self.assertTrue(running.contains(1))
        self.assertTrue(running.contains(17))
        self.assertFalse(running.contains(2))
        self.assertTrue(all(boxes.contains(n) for n in range(1, 50)))
        self.assertFalse(boxes.contains(0))
        self.assertFalse(boxes.contains(50))
        self.assertTrue(none.contains(0))
        self.assertFalse(none.contains(1))

    def test_rejects_a_span_that_breaks_its_parity(self) -> None:
        with self.assertRaises(ValueError):
            HouseNumberRange(2, 8, Parity.ODD, 1, 10, SeriesKind.STREET)
        with self.assertRaises(ValueError):
            HouseNumberRange(1, 4, Parity.ODD, 1, 10, SeriesKind.STREET)
        with self.assertRaises(ValueError):
            HouseNumberRange(1, 1, Parity.NO_NUMBER, 1, 10, SeriesKind.NO_HOUSE_NUMBER)

    def test_blank_source_parity_is_all(self) -> None:
        self.assertIs(Parity.from_source(""), Parity.ALL)
        self.assertIs(Parity.from_source("O"), Parity.ODD)
        with self.assertRaises(ValueError):
            Parity.from_source("A")


class LoaderTests(unittest.TestCase):
    def test_synthetic_files(self) -> None:
        with self._written() as data_dir:
            repo = DataLoader(data_dir).load()

        self.assertEqual(repo.street_name(1), "Teststraat")
        self.assertEqual(repo.street_name(2), "Andere AB")
        self.assertIsNone(repo.street_name(0))
        self.assertEqual(repo.city_name(10), "TESTSTAD")

        odd, even = repo.ranges_for("1011 aa")
        self.assertEqual(odd.parity, Parity.ODD)
        self.assertEqual(odd.kind, SeriesKind.STREET)
        self.assertEqual(even.from_number, 2)
        self.assertEqual(
            [range_.kind for range_ in repo.matching_ranges("1011AA", 4)],
            [SeriesKind.STREET],
        )
        self.assertEqual(repo.matching_ranges("1011AA", 4)[0].parity, Parity.EVEN)
        self.assertEqual(repo.matching_ranges("1011AA", 7), [])

        box = repo.matching_ranges("1000 AA", 10)[0]
        self.assertEqual(box.kind, SeriesKind.PO_BOX)
        self.assertEqual(box.street_id, 0)
        self.assertEqual(repo.matching_ranges("1000AA", 11), [])

        reply = repo.ranges_for("1000AB")[0]
        self.assertEqual(reply.kind, SeriesKind.REPLY_NUMBER)
        self.assertTrue(reply.contains(4))
        self.assertFalse(reply.contains(5))

        bare = repo.ranges_for("1011AB")[0]
        self.assertEqual(bare.kind, SeriesKind.NO_HOUSE_NUMBER)
        self.assertEqual(repo.street_name(bare.street_id), "Andere AB")
        self.assertEqual(repo.matching_ranges("1011AB", 0), [bare])

        low, high = repo.ranges_for("1011AC")
        self.assertEqual(low.parity, Parity.DOORLOPEND)
        self.assertTrue(low.contains(1))
        self.assertFalse(low.contains(2))
        self.assertTrue(high.contains(2))
        self.assertTrue(high.contains(4))

        self.assertEqual(repo.ranges_for("9999ZZ"), [])
        self.assertIn("postcodes=5", repr(repo))

    def test_unknown_street_is_rejected(self) -> None:
        with self._written(ranges="1~1011~AA~1~5~O~99~10\n") as data_dir:
            with self.assertRaises(DataFileError) as caught:
                DataLoader(data_dir).load()
        self.assertIn("street id 99", str(caught.exception))

    def test_postbus_with_a_street_is_rejected(self) -> None:
        with self._written(ranges="2~1000~AA~1~10~O~1~10\n") as data_dir:
            with self.assertRaises(DataFileError):
                DataLoader(data_dir).load()

    def test_short_row_is_rejected(self) -> None:
        with self._written(ranges="1~1011~AA~1~5~O~1\n") as data_dir:
            with self.assertRaises(DataFileError) as caught:
                DataLoader(data_dir).load()
        self.assertIn("expected 8 fields", str(caught.exception))

    def test_duplicate_street_id_is_rejected(self) -> None:
        with self._written(streets="1~A\n1~B\n") as data_dir:
            with self.assertRaises(DataFileError) as caught:
                DataLoader(data_dir).load()
        self.assertIn("duplicate street id 1", str(caught.exception))

    def test_missing_file(self) -> None:
        with self._written() as data_dir:
            (data_dir / "PCS_WPL.dat").unlink()
            with self.assertRaises(FileNotFoundError):
                create_repository(data_dir)

    def _written(
        self,
        *,
        streets: str = _STREETS + "\n",
        cities: str = _CITIES,
        ranges: str = _RANGES + "\n",
    ):
        import tempfile

        class _Dir:
            def __enter__(self) -> Path:
                self._tmp = tempfile.TemporaryDirectory()
                root = Path(self._tmp.name)
                (root / "PCS_STR.dat").write_text(streets, encoding="utf-8")
                (root / "PCS_WPL.dat").write_text(cities, encoding="utf-8")
                (root / "PCS_HNR.dat").write_text(ranges, encoding="utf-8")
                return root

            def __exit__(self, *exc: object) -> None:
                self._tmp.cleanup()

        return _Dir()


@unittest.skipUnless((DATA_DIR / "PCS_HNR.dat").is_file(), "PCS data files not present")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = create_repository(DATA_DIR)

    def test_counts(self) -> None:
        repo = self.repo
        self.assertEqual(len(repo.streets), 138_262)
        self.assertEqual(len(repo.cities), 2_458)
        self.assertEqual(len(repo.ranges_by_postcode), 472_488)
        self.assertEqual(
            sum(len(ranges) for ranges in repo.ranges_by_postcode.values()),
            629_336,
        )

    def test_known_addresses(self) -> None:
        repo = self.repo
        self.assertEqual(repo.streets[4].name, "'s Gravelandseveer")
        self.assertEqual(repo.cities[1000].name, "AMSTERDAM")

        ranges = repo.ranges_for("1011 AA")
        self.assertEqual(
            [(r.from_number, r.to_number, r.parity) for r in ranges],
            [(3, 9, Parity.ODD), (6, 10, Parity.EVEN)],
        )
        match = repo.matching_ranges("1011aa", 7)
        self.assertEqual(len(match), 1)
        self.assertEqual(repo.street_name(match[0].street_id), "De Ruyterkade Steigers")
        self.assertEqual(repo.city_name(match[0].city_id), "AMSTERDAM")
        self.assertEqual(repo.matching_ranges("1011 AA", 4), [])
        self.assertEqual(repo.matching_ranges("1011 AA", 6)[0].parity, Parity.EVEN)

        box = repo.matching_ranges("1000 AA", 25)
        self.assertEqual(len(box), 1)
        self.assertEqual(box[0].kind, SeriesKind.PO_BOX)
        self.assertIsNone(repo.street_name(box[0].street_id))
        self.assertEqual(repo.matching_ranges("1000 AA", 50), [])

        reply = repo.matching_ranges("1000 PA", 5)
        self.assertEqual(len(reply), 1)
        self.assertEqual(reply[0].kind, SeriesKind.REPLY_NUMBER)

        on_gracht = repo.ranges_for("1013LC")
        bare = [r for r in on_gracht if r.parity is Parity.NO_NUMBER]
        self.assertEqual(len(bare), 1)
        self.assertEqual(repo.street_name(bare[0].street_id), "Zoutkeetsgracht AB")
        self.assertTrue(bare[0].contains(0))
        self.assertFalse(bare[0].contains(1))
        numbered = repo.matching_ranges("1013 LC", 1)
        self.assertEqual(len(numbered), 1)
        self.assertEqual(repo.street_name(numbered[0].street_id), "Zoutkeetsgracht")

        running = repo.ranges_for("1011MR")
        self.assertEqual(
            [(r.from_number, r.to_number) for r in running],
            [(1, 17), (2, 18)],
        )
        self.assertTrue(all(r.parity is Parity.DOORLOPEND for r in running))
        self.assertEqual(
            [r.from_number for r in repo.matching_ranges("1011 MR", 2)],
            [2],
        )


if __name__ == "__main__":
    unittest.main()
