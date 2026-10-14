"""Dutch address validation against the PCS postcode files.

Load the three reference files with :func:`create_repository` and query
the returned :class:`InMemoryRepository` by postcode and house number.
"""

from address_validation.loader import (
    CITY_FILE,
    HOUSE_NUMBER_FILE,
    STREET_FILE,
    DataFileError,
    DataLoader,
    create_repository,
)
from address_validation.models import (
    MAX_HOUSE_NUMBER,
    City,
    HouseNumberRange,
    InMemoryRepository,
    Parity,
    SeriesKind,
    Street,
)
from address_validation.postcode import normalise_postcode

__all__ = [
    "CITY_FILE",
    "HOUSE_NUMBER_FILE",
    "MAX_HOUSE_NUMBER",
    "STREET_FILE",
    "City",
    "DataFileError",
    "DataLoader",
    "HouseNumberRange",
    "InMemoryRepository",
    "Parity",
    "SeriesKind",
    "Street",
    "create_repository",
    "normalise_postcode",
]
