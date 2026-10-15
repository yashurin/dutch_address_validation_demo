"""Identity of the PCS drop a service was loaded from."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from address_validation.loader import CITY_FILE, HOUSE_NUMBER_FILE, STREET_FILE
from address_validation.models import InMemoryRepository

_FILES = (HOUSE_NUMBER_FILE, STREET_FILE, CITY_FILE)


@dataclass(frozen=True, slots=True)
class ExtractFile:
    """One reference file, identified by its bytes."""

    name: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class ExtractRecord:
    """Counts for a loaded repository, plus file hashes when it came from disk.

    ``source`` is the directory the files were read from, or ``"repository"``
    when the service was given an already built repository. ``files`` is
    empty in that second case: there are no bytes to hash.
    """

    source: str
    files: tuple[ExtractFile, ...]
    postcodes: int
    streets: int
    cities: int
    ranges: int

    @classmethod
    def from_repository(
        cls,
        repository: InMemoryRepository,
        source: str = "repository",
    ) -> ExtractRecord:
        """Record counts for a repository that was not read from the PCS files."""
        return cls(
            source=source,
            files=(),
            postcodes=len(repository.ranges_by_postcode),
            streets=len(repository.streets),
            cities=len(repository.cities),
            ranges=sum(len(rows) for rows in repository.ranges_by_postcode.values()),
        )

    @classmethod
    def from_directory(
        cls,
        data_dir: str | Path,
        repository: InMemoryRepository,
    ) -> ExtractRecord:
        """Hash the three PCS files that produced ``repository``."""
        root = Path(data_dir).resolve()
        files = tuple(_stamp(root / name) for name in _FILES)
        counted = cls.from_repository(repository, source=str(root))
        return cls(
            source=counted.source,
            files=files,
            postcodes=counted.postcodes,
            streets=counted.streets,
            cities=counted.cities,
            ranges=counted.ranges,
        )


def _stamp(path: Path) -> ExtractFile:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return ExtractFile(name=path.name, sha256=digest.hexdigest(), size=size)
