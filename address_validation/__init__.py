"""Dutch address validation against the PCS postcode files.

Load the three reference files with :func:`create_repository` or
:meth:`AddressService.load`, then look up and validate addresses with
:class:`AddressService`.
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
from address_validation.normalise import normalise_extension, normalise_name
from address_validation.postcode import format_postcode, normalise_postcode
from address_validation.service import AddressService

__all__ = [
    "CITY_FILE",
    "HOUSE_NUMBER_FILE",
    "MAX_HOUSE_NUMBER",
    "STREET_FILE",
    "AddressService",
    "City",
    "DataFileError",
    "DataLoader",
    "HouseNumberRange",
    "InMemoryRepository",
    "Parity",
    "SeriesKind",
    "Street",
    "create_repository",
    "format_postcode",
    "normalise_extension",
    "normalise_name",
    "normalise_postcode",
]
