"""Queries against a live server loaded from the PCS files.

Expected lines are the published spellings for these addresses:
3811 MG 30 is Smallepad in Amersfoort (evens 2–90, odds 3–23),
1011 AA 7 is De Ruyterkade Steigers in Amsterdam, and 1000 AA is a
postbus in Amsterdam.
"""

from __future__ import annotations

import httpx
import pytest

_SMALLEPAD = ["Smallepad 30E", "3811 MG  AMERSFOORT"]
_CITY_TYPO = ["AMERSFOORT", "AKERSLOOT", "AMMERSTOL", "MERSELO", "STAMPERSGAT"]
_STREET_TYPO = [
    "Smallepad",
    "Westmallepad",
    "Smallekade",
    "Smallekamp",
    "Dallepad",
]


@pytest.mark.parametrize(
    ("params", "lines"),
    [
        (
            {"postcode": "3811 MG", "house_number": "30", "extension": "E"},
            _SMALLEPAD,
        ),
        (
            {"postcode": "3811mg", "house_number": "30", "extension": "e"},
            _SMALLEPAD,
        ),
        (
            {"postcode": "3811 MG", "house_number": "30"},
            ["Smallepad 30", "3811 MG  AMERSFOORT"],
        ),
        (
            {"postcode": "3811 MG", "house_number": "23"},
            ["Smallepad 23", "3811 MG  AMERSFOORT"],
        ),
        (
            {"postcode": "3811 MG", "house_number": "4"},
            ["Smallepad 4", "3811 MG  AMERSFOORT"],
        ),
        ({"postcode": "3811 MG", "house_number": "31"}, []),
        ({"postcode": "3811 MG", "house_number": "1"}, []),
        ({"postcode": "", "house_number": ""}, []),
        ({"postcode": "nope", "house_number": "30"}, []),
        (
            {"postcode": "1011 AA", "house_number": "7"},
            ["De Ruyterkade Steigers 7", "1011 AA  AMSTERDAM"],
        ),
        ({"postcode": "1011 AA", "house_number": "4"}, []),
        (
            {"postcode": "1011 KM", "house_number": "1"},
            ["'s Gravelandseveer 1", "1011 KM  AMSTERDAM"],
        ),
        (
            {"postcode": "1000 AA", "house_number": "25"},
            ["Postbus 25", "1000 AA  AMSTERDAM"],
        ),
        (
            {"postcode": "1011 MR", "house_number": "2"},
            ["Koerierstersplein 2", "1011 MR  AMSTERDAM"],
        ),
        ({"postcode": "1011 MR", "house_number": "19"}, []),
    ],
)
def test_lookup(
    api_client: httpx.Client,
    params: dict[str, str],
    lines: list[str],
) -> None:
    response = api_client.get("/api/v1/lookup", params=params)
    assert response.status_code == 200
    body = response.json()
    assert body == {"lines": lines}
    if lines:
        assert body["lines"][1].split("  ")[1] == lines[1].split("  ")[1]


def test_lookup_requires_postcode_and_house_number(api_client: httpx.Client) -> None:
    assert api_client.get("/api/v1/lookup").status_code == 422


@pytest.mark.parametrize(
    ("payload", "valid"),
    [
        (
            {
                "street": "Smallepad",
                "house_number": 30,
                "extension": "E",
                "postcode": "3811 MG",
                "city": "AMERSFOORT",
            },
            True,
        ),
        (
            {
                "street": "smallepad",
                "house_number": "30e",
                "postcode": "3811mg",
                "city": "amersfoort",
            },
            True,
        ),
        (
            {
                "street": "Smallepad",
                "house_number": 30,
                "postcode": "3811 MG",
                "city": "AMERSFOORT",
            },
            True,
        ),
        (
            {
                "street": "De Ruyterkade Steigers",
                "house_number": 7,
                "postcode": "1011 AA",
                "city": "amsterdam",
            },
            True,
        ),
        (
            {
                "street": "Postbus",
                "house_number": 25,
                "postcode": "1000 AA",
                "city": "AMSTERDAM",
            },
            True,
        ),
        (
            {
                "street": "Smallepad",
                "house_number": 31,
                "postcode": "3811 MG",
                "city": "AMERSFOORT",
            },
            False,
        ),
        (
            {
                "street": "Smallepad",
                "house_number": 30,
                "postcode": "3811 MG",
                "city": "UTRECHT",
            },
            False,
        ),
        (
            {
                "street": "",
                "house_number": 30,
                "postcode": "3811 MG",
                "city": "AMERSFOORT",
            },
            False,
        ),
        (
            {
                "street": "Smallepad",
                "house_number": 30,
                "postcode": "nope",
                "city": "AMERSFOORT",
            },
            False,
        ),
    ],
)
def test_validate(
    api_client: httpx.Client,
    payload: dict[str, object],
    valid: bool,
) -> None:
    response = api_client.post("/api/v1/validate", json=payload)
    assert response.status_code == 200
    assert response.json() == {"valid": valid}


def test_validate_rejects_a_partial_body(api_client: httpx.Client) -> None:
    response = api_client.post("/api/v1/validate", json={"street": "Smallepad"})
    assert response.status_code == 422


def test_correct_street(api_client: httpx.Client) -> None:
    scoped = api_client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "3811 MG"},
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"suggestions": ["Smallepad"]}

    district = api_client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "3811"},
    )
    assert district.json() == {"suggestions": ["Smallepad"]}

    other = api_client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "1011 AA"},
    )
    assert other.json() == {"suggestions": []}

    broad = api_client.get("/api/v1/correct/street", params={"street": "smallepd"})
    assert broad.json() == {"suggestions": _STREET_TYPO}

    empty = api_client.get(
        "/api/v1/correct/street",
        params={"street": "", "postcode": "3811 MG"},
    )
    assert empty.json() == {"suggestions": []}


def test_correct_city(api_client: httpx.Client) -> None:
    scoped = api_client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "3811 MG"},
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"suggestions": ["AMERSFOORT"]}

    district = api_client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "3811"},
    )
    assert district.json() == {"suggestions": ["AMERSFOORT"]}

    other = api_client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "1011 AA"},
    )
    assert other.json() == {"suggestions": []}

    broad = api_client.get("/api/v1/correct/city", params={"city": "amersfort"})
    assert broad.json() == {"suggestions": _CITY_TYPO}

    empty = api_client.get("/api/v1/correct/city", params={"city": "   "})
    assert empty.json() == {"suggestions": []}
    assert api_client.get("/api/v1/correct/city").status_code == 422
