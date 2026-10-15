"""Queries against a live server loaded from the PCS files.

Expected lines are the published spellings for these addresses:
3811 MG 30 is Smallepad in Amersfoort (evens 2–90, odds 3–23),
1011 AA 7 is De Ruyterkade Steigers in Amsterdam, and 1000 AA is a
postbus in Amsterdam.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

import httpx
import pytest

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

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
    if lines:
        assert body == {"lines": lines}
        assert body["lines"][1].split("  ")[1] == lines[1].split("  ")[1]
    else:
        assert body == {"lines": [], "reason": "not_found"}


@pytest.mark.parametrize(
    "params",
    [
        {"postcode": "", "house_number": ""},
        {"postcode": "nope", "house_number": "30"},
        {"postcode": "3811 MG", "house_number": "30", "extension": "no spaces"},
    ],
)
def test_lookup_rejects_malformed_input(
    api_client: httpx.Client,
    params: dict[str, str],
) -> None:
    response = api_client.get("/api/v1/lookup", params=params)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_ready_records_the_extract(api_client: httpx.Client) -> None:
    response = api_client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["source"] == str(_DATA_DIR.resolve())
    assert body["postcodes"] == 472_488
    assert body["streets"] == 138_262
    assert body["cities"] == 2_458
    assert body["ranges"] == 629_336
    by_name = {item["name"]: item for item in body["files"]}
    assert list(by_name) == ["PCS_HNR.dat", "PCS_STR.dat", "PCS_WPL.dat"]
    for name, item in by_name.items():
        raw = (_DATA_DIR / name).read_bytes()
        assert item["size"] == len(raw)
        assert item["sha256"] == hashlib.sha256(raw).hexdigest()


def test_validate_lines(api_client: httpx.Client) -> None:
    ok = api_client.post(
        "/api/v1/validate/lines",
        json={"lines": ["Smallepad 30E", "3811 MG  AMERSFOORT"]},
    )
    assert ok.status_code == 200
    assert ok.json() == {"valid": True}
    lowercase = api_client.post(
        "/api/v1/validate/lines",
        json={"lines": ["", "smallepad 30 e", "3811 mg amersfoort"]},
    )
    assert lowercase.json() == {"valid": True}
    miss = api_client.post(
        "/api/v1/validate/lines",
        json={"lines": ["Smallepad 31", "3811 MG  AMERSFOORT"]},
    )
    assert miss.json() == {"valid": False, "reason": "not_found"}
    unparsed = api_client.post(
        "/api/v1/validate/lines",
        json={"lines": ["Smallepad 30E", "not a postcode"]},
    )
    assert unparsed.status_code == 422
    assert (
        api_client.post(
            "/api/v1/validate/lines",
            json={"lines": ["Smallepad 30E"]},
        ).status_code
        == 422
    )


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
    ],
)
def test_validate(
    api_client: httpx.Client,
    payload: dict[str, object],
    valid: bool,
) -> None:
    response = api_client.post("/api/v1/validate", json=payload)
    assert response.status_code == 200
    if valid:
        assert response.json() == {"valid": True}
    else:
        assert response.json() == {"valid": False, "reason": "not_found"}


@pytest.mark.parametrize(
    "payload",
    [
        {
            "street": "",
            "house_number": 30,
            "postcode": "3811 MG",
            "city": "AMERSFOORT",
        },
        {
            "street": "Smallepad",
            "house_number": 30,
            "postcode": "nope",
            "city": "AMERSFOORT",
        },
    ],
)
def test_validate_rejects_malformed_input(
    api_client: httpx.Client,
    payload: dict[str, object],
) -> None:
    response = api_client.post("/api/v1/validate", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_validate_rejects_a_partial_body(api_client: httpx.Client) -> None:
    response = api_client.post("/api/v1/validate", json={"street": "Smallepad"})
    assert response.status_code == 422


def _suggestion_names(response: httpx.Response) -> list[str]:
    assert response.status_code == 200
    hits = response.json()["suggestions"]
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0.6 <= score <= 1 for score in scores)
    return [hit["name"] for hit in hits]


def test_correct_street(api_client: httpx.Client) -> None:
    scoped = api_client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "3811 MG"},
    )
    assert _suggestion_names(scoped) == ["Smallepad"]
    assert scoped.json()["suggestions"][0]["score"] == pytest.approx(
        difflib.SequenceMatcher(None, "smallepd", "smallepad").ratio()
    )

    district = api_client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "3811"},
    )
    assert _suggestion_names(district) == ["Smallepad"]

    other = api_client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "1011 AA"},
    )
    assert other.json() == {"suggestions": []}

    broad = api_client.get("/api/v1/correct/street", params={"street": "smallepd"})
    assert _suggestion_names(broad) == _STREET_TYPO

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
    assert _suggestion_names(scoped) == ["AMERSFOORT"]
    assert scoped.json()["suggestions"][0]["score"] < 1

    district = api_client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "3811"},
    )
    assert _suggestion_names(district) == ["AMERSFOORT"]

    other = api_client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "1011 AA"},
    )
    assert other.json() == {"suggestions": []}

    broad = api_client.get("/api/v1/correct/city", params={"city": "amersfort"})
    assert _suggestion_names(broad) == _CITY_TYPO

    exact = api_client.get("/api/v1/correct/city", params={"city": "Amsterdam"})
    assert exact.json() == {"suggestions": [{"name": "AMSTERDAM", "score": 1.0}]}
    # Rotterdam scores about 0.67, but closer names fill the five slots.
    neighbours = api_client.get(
        "/api/v1/correct/city",
        params={"city": "Amsterdam", "include_neighbours": "true"},
    )
    assert _suggestion_names(neighbours) == [
        "AMSTERDAM",
        "NIEUW-AMSTERDAM",
        "AMSTENRADE",
        "ZWAMMERDAM",
        "STEENDAM",
    ]
    assert neighbours.json()["suggestions"][0]["score"] == 1.0

    empty = api_client.get("/api/v1/correct/city", params={"city": "   "})
    assert empty.json() == {"suggestions": []}
    assert api_client.get("/api/v1/correct/city").status_code == 422
