"""HTTP API for Dutch address validation.

The process loads the PCS files once, during startup, and serves that
in-memory repository. Pass a repository to :func:`create_app` to skip the
files, which is what the tests do.

Run it from the repository root, so ``data/`` is the default directory::

    address-validation-api

``ADDRESS_DATA_DIR`` selects another directory. ``ADDRESS_HOST`` and
``ADDRESS_PORT`` select the bind address (``127.0.0.1:8000`` by default).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from address_validation.models import InMemoryRepository
from address_validation.schemas import (
    LookupResponse,
    SuggestionResponse,
    ValidateRequest,
    ValidateResponse,
)
from address_validation.service import AddressService

log = logging.getLogger("uvicorn.error")

_API_PREFIX = "/api/v1"


def get_service(request: Request) -> AddressService:
    """Return the repository loaded during startup."""
    service = getattr(request.app.state, "service", None)
    if not isinstance(service, AddressService):
        raise HTTPException(status_code=503, detail="address data is not loaded")
    return service


Service = Annotated[AddressService, Depends(get_service)]


def create_app(
    repository: InMemoryRepository | None = None,
    data_dir: str | Path | None = None,
) -> FastAPI:
    """Build the API.

    ``repository`` is used as-is when it is given. Otherwise the three PCS
    files in ``data_dir`` are loaded on startup. ``data_dir`` defaults to
    the ``ADDRESS_DATA_DIR`` environment variable, then to ``data``.
    """
    if data_dir is None:
        data_dir = os.environ.get("ADDRESS_DATA_DIR", "data")
    source = Path(data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if repository is not None:
            service = AddressService(repository)
            origin = "supplied repository"
        else:
            service = AddressService.load(source)
            origin = str(source)
        app.state.service = service
        log.info("Loaded %s (%s)", service.repository, origin)
        yield
        app.state.service = None

    app = FastAPI(
        title="Dutch address validation",
        summary="Validate, look up, and correct Dutch addresses from the PCS files.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.post(_API_PREFIX + "/validate", response_model=ValidateResponse)
    def validate(body: ValidateRequest, service: Service) -> ValidateResponse:
        """Return whether this street, number, postcode, and city occur together.

        Comparison ignores case, spacing, and apostrophe variants. Odd and
        even house numbers follow the range in the file. A missing extension
        is valid. A malformed extension makes the address invalid. Unknown
        input returns ``{"valid": false}`` rather than an error.
        """
        valid = service.validate(
            body.street,
            body.house_number,
            body.extension,
            body.postcode,
            body.city,
        )
        return ValidateResponse(valid=valid)

    @app.get(_API_PREFIX + "/lookup", response_model=LookupResponse)
    def lookup(
        service: Service,
        postcode: Annotated[
            str,
            Query(description="PC6, with or without a space.", examples=["3811 MG"]),
        ],
        house_number: Annotated[
            str,
            Query(
                description='House number. May include the extension, as in "30E".',
                examples=["30"],
            ),
        ],
        extension: Annotated[
            str | None,
            Query(description="Optional toevoeging, such as E or bis.", examples=["E"]),
        ] = None,
    ) -> LookupResponse:
        """Return the two-line postal address for a postcode and house number.

        The result is ``{"lines": []}`` when nothing matches. An even number
        does not match an odd range.
        """
        lines = service.lookup_address(postcode, house_number, extension)
        return LookupResponse(lines=lines)

    @app.get(_API_PREFIX + "/correct/street", response_model=SuggestionResponse)
    def correct_street(
        service: Service,
        street: Annotated[str, Query(description="Street name, possibly mistyped.")],
        postcode: Annotated[
            str | None,
            Query(
                description=(
                    "Optional PC4 or PC6. Restricts the search to that "
                    "district or postcode. Omit it to search every street; "
                    "that takes a few hundred milliseconds."
                ),
                examples=["3811 MG"],
            ),
        ] = None,
    ) -> SuggestionResponse:
        """Suggest published street spellings for a mistyped name."""
        return SuggestionResponse(
            suggestions=service.correct_street(street, postcode),
        )

    @app.get(_API_PREFIX + "/correct/city", response_model=SuggestionResponse)
    def correct_city(
        service: Service,
        city: Annotated[str, Query(description="City name, possibly mistyped.")],
        postcode: Annotated[
            str | None,
            Query(
                description=(
                    "Optional PC4 or PC6. Restricts the search to the cities "
                    "on that postcode or in that district. Omit it to search "
                    "every city."
                ),
                examples=["3811"],
            ),
        ] = None,
    ) -> SuggestionResponse:
        """Suggest published city spellings for a mistyped name."""
        return SuggestionResponse(suggestions=service.correct_city(city, postcode))

    return app


app = create_app()


def main() -> None:
    """Load the PCS files and serve the API."""
    import uvicorn

    host = os.environ.get("ADDRESS_HOST", "127.0.0.1")
    port = int(os.environ.get("ADDRESS_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
