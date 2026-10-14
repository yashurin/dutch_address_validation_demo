"""Shared fixtures.

``repository`` parses the three PCS files once per session.
``service`` is the in-memory repository those tests call. A lookup does
not read the files again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from address_validation import AddressService, InMemoryRepository, create_repository

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_FILES = ("PCS_HNR.dat", "PCS_STR.dat", "PCS_WPL.dat")


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Directory with the PCS reference files."""
    missing = [name for name in _FILES if not (_DATA_DIR / name).is_file()]
    if missing:
        pytest.skip("PCS data files not present: " + ", ".join(missing))
    return _DATA_DIR


@pytest.fixture(scope="session")
def repository(data_dir: Path) -> InMemoryRepository:
    """The loaded postcode repository, shared by every test that needs it."""
    return create_repository(data_dir)


@pytest.fixture(scope="session")
def service(repository: InMemoryRepository) -> AddressService:
    """Address service over the session repository."""
    return AddressService(repository)
