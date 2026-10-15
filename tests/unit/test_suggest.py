"""City and street suggestions.

Scoped queries run against the session repository. Ranking rules that need
a catalogue of a few names use a separate in-memory service, so the
unscoped national street scan happens only once.
"""

from __future__ import annotations

import difflib

import pytest

from address_validation import (
    PO_BOX_STREET,
    AddressService,
    City,
    HouseNumberRange,
    InMemoryRepository,
    Parity,
    SeriesKind,
    Street,
    Suggestion,
)
from address_validation.suggest import SUGGESTION_LIMIT, rank_suggestions


def _names(suggestions: list[Suggestion]) -> list[str]:
    return [item.name for item in suggestions]


_CITY_TYPO = ["AMERSFOORT", "AKERSLOOT", "AMMERSTOL", "MERSELO", "STAMPERSGAT"]
_STREET_TYPO = [
    "Smallepad",
    "Westmallepad",
    "Smallekade",
    "Smallekamp",
    "Dallepad",
]


def test_correct_city_with_and_without_postcode(service: AddressService) -> None:
    scoped = service.correct_city("amersfort", "3811 MG")
    assert _names(scoped) == ["AMERSFOORT"]
    assert scoped[0].score == pytest.approx(
        difflib.SequenceMatcher(None, "amersfort", "amersfoort").ratio()
    )
    assert _names(service.correct_city("amersfort", "3811")) == ["AMERSFOORT"]
    assert service.correct_city("amersfort", "1011 AA") == []
    assert _names(service.correct_city("amersfort")) == _CITY_TYPO
    assert service.correct_city("amersfort", postcode=None) == service.correct_city(
        "amersfort"
    )


def test_correct_street_with_and_without_postcode(service: AddressService) -> None:
    assert _names(service.correct_street("smallepd", "3811 MG")) == ["Smallepad"]
    assert _names(service.correct_street("smallepd", " 3811 ")) == ["Smallepad"]
    assert service.correct_street("smallepd", "1011 AA") == []
    broad = service.correct_street("smallepd")
    assert _names(broad) == _STREET_TYPO
    assert service.correct_street("smallepd", postcode=None) == broad
    assert len(broad) == len({item.name for item in broad})


@pytest.mark.parametrize("method_name", ["correct_city", "correct_street"])
@pytest.mark.parametrize(
    ("query", "postcode"),
    [
        ("", None),
        ("", "3811 MG"),
        ("   ", None),
        ("   ", "3811 MG"),
        ("x", ""),
        ("x", "nope"),
        ("x", "3811 M"),
        ("x", "0100"),
    ],
)
def test_correction_rejects_empty_input_and_invalid_postcode(
    service: AddressService,
    method_name: str,
    query: str,
    postcode: str | None,
) -> None:
    correct = getattr(service, method_name)
    assert correct(query, postcode) == []


def test_equal_scores_use_the_published_name() -> None:
    published = ("Kerkstraat", "Kerk straat", "Kerkstraat")
    normalised = ("kerkstraat", "kerkstraat", "kerkstraat")
    ranked = rank_suggestions("kerkstraat", normalised, published, None)
    assert _names(ranked) == ["Kerk straat", "Kerkstraat"]
    assert [item.score for item in ranked] == [1.0, 1.0]


def test_exact_match_hides_neighbours_unless_asked() -> None:
    published = ("AMSTERDAM", "ROTTERDAM")
    normalised = ("amsterdam", "rotterdam")
    alone = rank_suggestions("amsterdam", normalised, published, None)
    assert _names(alone) == ["AMSTERDAM"]
    assert alone[0].score == 1.0
    both = rank_suggestions(
        "amsterdam",
        normalised,
        published,
        None,
        include_neighbours=True,
    )
    assert _names(both) == ["AMSTERDAM", "ROTTERDAM"]
    assert both[1].score == pytest.approx(
        difflib.SequenceMatcher(None, "amsterdam", "rotterdam").ratio()
    )


def test_limit_keeps_the_best_names() -> None:
    published = tuple(f"Name {index}" for index in range(SUGGESTION_LIMIT + 1))
    normalised = ("same",) * len(published)
    ranked = rank_suggestions("same", normalised, published, None)
    assert _names(ranked) == sorted(published, key=str.lower)[:SUGGESTION_LIMIT]


@pytest.fixture
def sample_service() -> AddressService:
    ranges = {
        "1011AA": [
            HouseNumberRange(1, 9, Parity.ODD, 1, 1000, SeriesKind.STREET),
        ],
        "1011AB": [
            HouseNumberRange(1, 9, Parity.ODD, 2, 1000, SeriesKind.STREET),
        ],
        "1011AC": [
            HouseNumberRange(1, 9, Parity.ODD, 3, 1000, SeriesKind.STREET),
        ],
        "1011AD": [
            HouseNumberRange(1, 9, Parity.ODD, 4, 1000, SeriesKind.STREET),
        ],
        "1011AE": [
            HouseNumberRange(1, 9, Parity.ODD, 5, 1000, SeriesKind.STREET),
        ],
        "1012AA": [
            HouseNumberRange(1, 5, Parity.ODD, 7, 1000, SeriesKind.STREET),
        ],
        "3011AA": [
            HouseNumberRange(1, 9, Parity.ODD, 6, 2000, SeriesKind.STREET),
        ],
        "1000AA": [
            HouseNumberRange(1, 10, Parity.ALL, 0, 1000, SeriesKind.PO_BOX),
        ],
    }
    streets = {
        1: Street(1, "De Ruyterkade Steigers"),
        2: Street(2, "De Ruyterkade"),
        3: Street(3, "Kerkstraat"),
        4: Street(4, "Kerkstraat"),
        5: Street(5, "Klerkstraat"),
        6: Street(6, "Kalverstraat"),
        7: Street(7, "'s Gravelandseveer"),
    }
    cities = {
        1000: City(1000, "AMSTERDAM"),
        2000: City(2000, "ROTTERDAM"),
    }
    return AddressService(
        InMemoryRepository(
            ranges_by_postcode=ranges,
            streets=streets,
            cities=cities,
        )
    )


def test_suggestion_index_is_built_with_the_service(
    sample_service: AddressService,
) -> None:
    index = sample_service.suggestion_index
    assert "AMSTERDAM" in index.cities.published
    assert index is sample_service.suggestion_index


def test_sample_scope_ranks_unique_names(sample_service: AddressService) -> None:
    service = sample_service
    # Folded "amsterdam" and "rotterdam" score about 0.67. The exact
    # spelling is returned alone. The typo stays under the neighbour.
    assert _names(service.correct_city("amsterdm")) == ["AMSTERDAM"]
    exact = service.correct_city("  AmSterDaM ")
    assert _names(exact) == ["AMSTERDAM"]
    assert exact[0].score == 1.0
    neighbours = service.correct_city("  AmSterDaM ", include_neighbours=True)
    assert _names(neighbours) == ["AMSTERDAM", "ROTTERDAM"]
    assert neighbours[0].score == 1.0
    assert service.correct_city("amsterdm", include_neighbours=True) == (
        service.correct_city("amsterdm")
    )
    assert _names(service.correct_city("amsterdm", "1011 AA")) == ["AMSTERDAM"]
    assert _names(service.correct_city("amsterdm", " 1011 ")) == ["AMSTERDAM"]
    assert _names(service.correct_city("rotterdm", "3011AA")) == ["ROTTERDAM"]
    assert service.correct_city("amsterdm", "3011 AA") == []
    assert service.correct_city("rotterdm", "1011") == []

    scoped = _names(service.correct_street("kerkstr", "1011"))
    assert scoped[0] == "Kerkstraat"
    assert scoped.count("Kerkstraat") == 1
    assert scoped.index("Kerkstraat") < scoped.index("Klerkstraat")
    assert "Kalverstraat" not in scoped
    assert _names(service.correct_street("kerkstr", "1011 AC")) == ["Kerkstraat"]
    assert _names(service.correct_street("de ruyterkade steiger", "1011AA")) == [
        "De Ruyterkade Steigers"
    ]
    assert _names(service.correct_street("de ruyterkade steiger", "1011 AB")) == [
        "De Ruyterkade"
    ]
    district = _names(service.correct_street("de ruyterkade steiger", "1011"))
    assert district.index("De Ruyterkade Steigers") < district.index("De Ruyterkade")
    assert _names(service.correct_street("kalverstr"))[0] == "Kalverstraat"
    assert _names(service.correct_street("kalverstr", postcode=None))[0] == (
        "Kalverstraat"
    )

    assert _names(service.correct_street("postbux", "1000 AA")) == [PO_BOX_STREET]
    assert service.correct_street("postbux", "1011 AA") == []
    assert _names(service.correct_street("postbux")) == [PO_BOX_STREET]
    assert _names(service.correct_street("\u2019s gravelandseveer", "1012 aa")) == [
        "'s Gravelandseveer"
    ]
    assert _names(service.correct_street("gravelandseveer", "1012AA"))[0] == (
        "'s Gravelandseveer"
    )
