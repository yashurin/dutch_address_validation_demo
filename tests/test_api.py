"""HTTP API against an in-memory repository.

These tests do not parse the PCS files.
"""

from __future__ import annotations

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
    assert missing.json() == {"lines": []}


def test_lookup_rejects_a_missing_query(client: TestClient) -> None:
    assert client.get("/api/v1/lookup").status_code == 422
    empty = client.get(
        "/api/v1/lookup",
        params={"postcode": "", "house_number": ""},
    )
    assert empty.status_code == 200
    assert empty.json() == {"lines": []}


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
    assert wrong.json() == {"valid": False}
    bad_postcode = client.post(
        "/api/v1/validate",
        json={
            "street": "Smallepad",
            "house_number": 30,
            "postcode": "nope",
            "city": "AMERSFOORT",
        },
    )
    assert bad_postcode.json() == {"valid": False}


def test_validate_rejects_a_partial_body(client: TestClient) -> None:
    response = client.post("/api/v1/validate", json={"street": "Smallepad"})
    assert response.status_code == 422


def test_correct_street_and_city_with_and_without_postcode(client: TestClient) -> None:
    street = client.get(
        "/api/v1/correct/street",
        params={"street": "smallepd", "postcode": "3811 MG"},
    )
    assert street.json() == {"suggestions": ["Smallepad"]}
    broad_street = client.get("/api/v1/correct/street", params={"street": "smallepd"})
    assert broad_street.json()["suggestions"][0] == "Smallepad"

    city = client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "3811"},
    )
    assert city.json() == {"suggestions": ["AMERSFOORT"]}
    other_postcode = client.get(
        "/api/v1/correct/city",
        params={"city": "amersfort", "postcode": "1011 AA"},
    )
    assert other_postcode.json() == {"suggestions": []}
    broad_city = client.get("/api/v1/correct/city", params={"city": "amersfort"})
    assert broad_city.json()["suggestions"][0] == "AMERSFOORT"


def test_correction_rejects_empty_input(client: TestClient) -> None:
    assert client.get(
        "/api/v1/correct/street",
        params={"street": "", "postcode": "3811 MG"},
    ).json() == {"suggestions": []}
    assert client.get("/api/v1/correct/city", params={"city": "   "}).json() == {
        "suggestions": []
    }
    assert client.get("/api/v1/correct/city").status_code == 422


def test_openapi_lists_the_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/validate"]
    assert "get" in paths["/api/v1/lookup"]
    assert "get" in paths["/api/v1/correct/street"]
    assert "get" in paths["/api/v1/correct/city"]


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
    assert response.json() == {"suggestions": ["AMERSFOORT"]}


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
