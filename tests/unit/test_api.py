"""HTTP API against an in-memory repository.

These tests do not parse the PCS files.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from address_validation import (
    City,
    HouseNumberRange,
    InMemoryRepository,
    Parity,
    SeriesKind,
    Street,
)
from address_validation.api import create_app
from address_validation.service import AddressService


def _repository() -> InMemoryRepository:
    return InMemoryRepository(
        ranges_by_postcode={
            "3811MG": [
                HouseNumberRange(2, 90, Parity.EVEN, 1, 3800, SeriesKind.STREET),
                HouseNumberRange(3, 23, Parity.ODD, 1, 3800, SeriesKind.STREET),
            ],
            "1011AA": [
                HouseNumberRange(1, 9, Parity.ODD, 2, 1000, SeriesKind.STREET),
            ],
        },
        streets={
            1: Street(1, "Smallepad"),
            2: Street(2, "De Ruyterkade Steigers"),
        },
        cities={
            3800: City(3800, "AMERSFOORT"),
            1000: City(1000, "AMSTERDAM"),
        },
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(repository=_repository())
    with TestClient(app) as test_client:
        yield test_client


def test_lookup_known_address(client: TestClient) -> None:
    response = client.get(
        "/api/v1/lookup",
        params={"postcode": "3811 MG", "house_number": "30", "extension": "E"},
    )
    assert response.status_code == 200
    assert response.json() == {"lines": ["Smallepad 30E", "3811 MG  AMERSFOORT"]}


def test_lookup_without_extension_and_outside_the_odd_range(client: TestClient) -> None:
    bare = client.get(
        "/api/v1/lookup",
        params={"postcode": "3811mg", "house_number": "30"},
    )
    assert bare.json() == {"lines": ["Smallepad 30", "3811 MG  AMERSFOORT"]}
    odd = client.get(
        "/api/v1/lookup",
        params={"postcode": "3811 MG", "house_number": "23"},
    )
    assert odd.json()["lines"][0] == "Smallepad 23"
    missing = client.get(
        "/api/v1/lookup",
        params={"postcode": "3811 MG", "house_number": "31"},
    )
    assert missing.status_code == 200
    assert missing.json() == {"lines": [], "reason": "not_found"}


def test_lookup_rejects_a_missing_query(client: TestClient) -> None:
    assert client.get("/api/v1/lookup").status_code == 422
    empty = client.get(
        "/api/v1/lookup",
        params={"postcode": "", "house_number": ""},
    )
    assert empty.status_code == 422
    assert isinstance(empty.json()["detail"], str)
    bad_extension = client.get(
        "/api/v1/lookup",
        params={
            "postcode": "3811 MG",
            "house_number": "30",
            "extension": "no spaces",
        },
    )
    assert bad_extension.status_code == 422


def test_validate_success_and_failure(client: TestClient) -> None:
    ok = client.post(
        "/api/v1/validate",
        json={
            "street": "smallepad",
            "house_number": 30,
            "extension": "e",
            "postcode": "3811mg",
            "city": "amersfoort",
        },
    )
    assert ok.status_code == 200
    assert ok.json() == {"valid": True}

    missing_extension = client.post(
        "/api/v1/validate",
        json={
            "street": "Smallepad",
            "house_number": "30",
            "postcode": "3811 MG",
            "city": "AMERSFOORT",
        },
    )
    assert missing_extension.json() == {"valid": True}

    wrong = client.post(
        "/api/v1/validate",
        json={
            "street": "Smallepad",
            "house_number": 31,
            "postcode": "3811 MG",
            "city": "AMERSFOORT",
        },
    )
    assert wrong.json() == {"valid": False, "reason": "not_found"}
    bad_postcode = client.post(
        "/api/v1/validate",
        json={
            "street": "Smallepad",
            "house_number": 30,
            "postcode": "nope",
            "city": "AMERSFOORT",
        },
    )
    assert bad_postcode.status_code == 422
    assert "postcode" in bad_postcode.json()["detail"]


def test_validate_rejects_a_partial_body(client: TestClient) -> None:
    response = client.post("/api/v1/validate", json={"street": "Smallepad"})
    assert response.status_code == 422


def test_correct_street_and_city_with_and_without_postcode(client: TestClient) -> None:
    street = client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "3811 MG"},
    )
    street_hit = street.json()["suggestions"]
    assert [hit["name"] for hit in street_hit] == ["Smallepad"]
    assert street_hit[0]["score"] == pytest.approx(
        difflib.SequenceMatcher(None, "smallepd", "smallepad").ratio()
    )
    broad_street = client.get("/api/v1/correct/street", params={"street": "smallepd"})
    assert broad_street.json()["suggestions"][0]["name"] == "Smallepad"

    city = client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "3811"},
    )
    city_hit = city.json()["suggestions"]
    assert [hit["name"] for hit in city_hit] == ["AMERSFOORT"]
    assert city_hit[0]["score"] == pytest.approx(
        difflib.SequenceMatcher(None, "amersfort", "amersfoort").ratio()
    )
    other_postcode = client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "1011 AA"},
    )
    assert other_postcode.json() == {"suggestions": []}
    broad_city = client.get("/api/v1/correct/city", params={"city": "amersfort"})
    assert broad_city.json()["suggestions"][0]["name"] == "AMERSFOORT"


def test_correction_rejects_empty_input(client: TestClient) -> None:
    assert client.get(
        "/api/v1/correct/street",
        params={"street": "", "postcode": "3811 MG"},
    ).json() == {"suggestions": []}
    assert client.get("/api/v1/correct/city", params={"city": "   "}).json() == {
        "suggestions": []
    }
    assert client.get("/api/v1/correct/city").status_code == 422


def test_validate_lines_uses_the_two_line_form(client: TestClient) -> None:
    ok = client.post(
        "/api/v1/validate/lines",
        json={"lines": ["", "Smallepad 30E", "3811 MG  AMERSFOORT"]},
    )
    assert ok.status_code == 200
    assert ok.json() == {"valid": True}
    miss = client.post(
        "/api/v1/validate/lines",
        json={"lines": ["Smallepad 31", "3811 MG  AMERSFOORT"]},
    )
    assert miss.json() == {"valid": False, "reason": "not_found"}
    unparsed = client.post(
        "/api/v1/validate/lines",
        json={"lines": ["Smallepad 30E", "not a postcode"]},
    )
    assert unparsed.status_code == 422
    shape = client.post("/api/v1/validate/lines", json={"lines": ["Smallepad 30E"]})
    assert shape.status_code == 422


def test_ready_reports_a_supplied_repository(client: TestClient) -> None:
    body = client.get("/api/v1/ready").json()
    assert body["ready"] is True
    assert body["source"] == "repository"
    assert body["files"] == []
    assert body["postcodes"] == 2
    assert body["streets"] == 2
    assert body["cities"] == 2
    assert body["ranges"] == 3


def test_openapi_lists_the_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/validate"]
    assert "post" in paths["/api/v1/validate/lines"]
    assert "get" in paths["/api/v1/ready"]
    assert "get" in paths["/api/v1/lookup"]
    assert "get" in paths["/api/v1/correct/street"]
    assert "get" in paths["/api/v1/correct/city"]
    street_params = paths["/api/v1/correct/street"]["get"]["parameters"]
    assert any(param["name"] == "include_neighbours" for param in street_params)
    document = client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]
    assert "reason" not in schemas["ValidateMatch"]["properties"]
    assert schemas["ValidateMatch"]["properties"]["valid"]["const"] is True
    assert schemas["ValidateMiss"]["properties"]["reason"]["const"] == "not_found"
    examples = document["paths"]["/api/v1/validate"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    assert examples["match"]["value"] == {"valid": True}
    assert examples["not_found"]["value"] == {"valid": False, "reason": "not_found"}


def test_startup_loads_the_data_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen: dict[str, Path] = {}

    def fake_load(
        cls: type[AddressService], data_dir: str | Path = "data"
    ) -> AddressService:
        seen["data_dir"] = Path(data_dir)
        return cls(_repository())

    monkeypatch.setattr(AddressService, "load", classmethod(fake_load))
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/v1/lookup",
            params={"postcode": "3811 MG", "house_number": "30", "extension": "E"},
        )
    assert response.json()["lines"][0] == "Smallepad 30E"
    assert seen["data_dir"] == tmp_path


def test_repository_argument_skips_the_files(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_load(
        cls: type[AddressService], data_dir: str | Path = "data"
    ) -> AddressService:
        raise AssertionError(data_dir)

    monkeypatch.setattr(AddressService, "load", classmethod(fail_load))
    app = create_app(repository=_repository())
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/v1/correct/city",
            params={"city": "amersfort", "postcode": "3811 MG"},
        )
    assert response.json()["suggestions"][0]["name"] == "AMERSFOORT"


def test_exact_city_can_include_neighbours() -> None:
    repository = InMemoryRepository(
        ranges_by_postcode={
            "1011AA": [
                HouseNumberRange(1, 9, Parity.ODD, 1, 1000, SeriesKind.STREET),
            ],
            "3011AA": [
                HouseNumberRange(1, 9, Parity.ODD, 1, 2000, SeriesKind.STREET),
            ],
        },
        streets={1: Street(1, "Kalverstraat")},
        cities={
            1000: City(1000, "AMSTERDAM"),
            2000: City(2000, "ROTTERDAM"),
        },
    )
    with TestClient(create_app(repository=repository)) as client:
        exact = client.get("/api/v1/correct/city", params={"city": "Amsterdam"})
        assert exact.json() == {"suggestions": [{"name": "AMSTERDAM", "score": 1.0}]}
        wide = client.get(
            "/api/v1/correct/city",
            params={"city": "Amsterdam", "include_neighbours": "true"},
        )
        hits = wide.json()["suggestions"]
        assert [hit["name"] for hit in hits] == ["AMSTERDAM", "ROTTERDAM"]
        assert hits[0]["score"] == 1.0
        assert hits[1]["score"] == pytest.approx(
            difflib.SequenceMatcher(None, "amsterdam", "rotterdam").ratio()
        )


def test_lookup_reports_an_ambiguous_number() -> None:
    repository = InMemoryRepository(
        ranges_by_postcode={
            "2000AB": [
                HouseNumberRange(1, 9, Parity.ODD, 1, 1000, SeriesKind.STREET),
                HouseNumberRange(1, 9, Parity.ODD, 2, 1000, SeriesKind.STREET),
            ],
        },
        streets={
            1: Street(1, "Eerste Straat"),
            2: Street(2, "Tweede Straat"),
        },
        cities={1000: City(1000, "AMSTERDAM")},
    )
    with TestClient(create_app(repository=repository)) as client:
        lookup = client.get(
            "/api/v1/lookup",
            params={"postcode": "2000 AB", "house_number": "1"},
        )
        assert lookup.status_code == 200
        assert lookup.json() == {"lines": [], "reason": "ambiguous"}
        named = client.post(
            "/api/v1/validate",
            json={
                "street": "Tweede Straat",
                "house_number": 1,
                "postcode": "2000 AB",
                "city": "AMSTERDAM",
            },
        )
        assert named.json() == {"valid": True}


def test_address_data_dir_is_the_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen: dict[str, Path] = {}

    def fake_load(
        cls: type[AddressService], data_dir: str | Path = "data"
    ) -> AddressService:
        seen["data_dir"] = Path(data_dir)
        return cls(_repository())

    monkeypatch.setenv("ADDRESS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(AddressService, "load", classmethod(fake_load))
    with TestClient(create_app()):
        pass
    assert seen["data_dir"] == tmp_path
