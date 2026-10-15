"""HTTP API for Dutch address validation.

The process loads the PCS files during startup, and serves that
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
from fastapi.responses import JSONResponse

from address_validation.models import InMemoryRepository
from address_validation.schemas import (
    ExtractFileResponse,
    LookupResponse,
    ReadyResponse,
    SuggestionHit,
    SuggestionResponse,
    ValidateLinesRequest,
    ValidateMatch,
    ValidateMiss,
    ValidateRequest,
    ValidateResponse,
)
from address_validation.service import AddressService, InvalidAddress
from address_validation.suggest import Suggestion

log = logging.getLogger("uvicorn.error")

_API_PREFIX = "/api/v1"
_VALIDATE_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "examples": {
                    "match": {
                        "summary": "The address is in the extract",
                        "value": {"valid": True},
                    },
                    "not_found": {
                        "summary": "The address parsed and is absent",
                        "value": {"valid": False, "reason": "not_found"},
                    },
                }
            }
        }
    }
}


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
        else:
            service = AddressService.load(source)
        app.state.service = service
        stamps = ",".join(
            f"{item.name}={item.sha256[:12]}" for item in service.extract.files
        )
        log.info(
            "Loaded %s from %s (%s)",
            service.repository,
            service.extract.source,
            stamps or "no file hashes",
        )
        yield
        app.state.service = None

    app = FastAPI(
        title="Dutch address validation",
        summary="Validate, look up, and correct Dutch addresses from the PCS files.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(InvalidAddress)
    async def reject_invalid_address(
        _request: Request,
        exc: InvalidAddress,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.post(
        _API_PREFIX + "/validate",
        response_model=ValidateResponse,
        responses=_VALIDATE_RESPONSES,
    )
    def validate(body: ValidateRequest, service: Service) -> ValidateResponse:
        """Return whether this street, number, postcode, and city occur together.

        Comparison ignores case, spacing, and apostrophe variants. Odd and
        even house numbers follow the range in the file. A missing extension
        is valid. A postcode, house number, extension, or name the parser
        rejects is HTTP 422. A parsed address that is not in the extract
        returns ``{"valid": false, "reason": "not_found"}``.
        """
        valid = service.validate(
            body.street,
            body.house_number,
            body.extension,
            body.postcode,
            body.city,
        )
        if valid:
            return ValidateMatch(valid=True)
        return ValidateMiss(valid=False, reason="not_found")

    @app.post(
        _API_PREFIX + "/validate/lines",
        response_model=ValidateResponse,
        responses=_VALIDATE_RESPONSES,
    )
    def validate_lines(
        body: ValidateLinesRequest,
        service: Service,
    ) -> ValidateResponse:
        """Validate the two-line postal form.

        The body must contain exactly two non-blank lines. A line that does
        not parse is HTTP 422. A parsed address that is not in the extract
        returns ``{"valid": false, "reason": "not_found"}``.
        """
        if service.validate_lines(body.lines):
            return ValidateMatch(valid=True)
        return ValidateMiss(valid=False, reason="not_found")

    @app.get(_API_PREFIX + "/ready", response_model=ReadyResponse)
    def ready(service: Service) -> ReadyResponse:
        """Report the extract loaded during startup.

        The process accepts requests only after this data is in memory,
        including the suggestion index. ``files`` is empty when the app was
        given a repository instead of a directory.
        """
        record = service.extract
        return ReadyResponse(
            ready=True,
            source=record.source,
            postcodes=record.postcodes,
            streets=record.streets,
            cities=record.cities,
            ranges=record.ranges,
            files=[
                ExtractFileResponse(name=item.name, sha256=item.sha256, size=item.size)
                for item in record.files
            ],
        )

    @app.get(
        _API_PREFIX + "/lookup",
        response_model=LookupResponse,
        response_model_exclude_none=True,
    )
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

        A parsed postcode that does not contain the number returns
        ``{"lines": [], "reason": "not_found"}``. More than one street
        returns ``{"reason": "ambiguous"}``. A postcode, house number, or
        extension the parser rejects is HTTP 422. An even number does not
        match an odd range.
        """
        found = service.lookup_address(postcode, house_number, extension)
        return LookupResponse(lines=list(found.lines), reason=found.reason)

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
        include_neighbours: Annotated[
            bool,
            Query(
                description=(
                    "When the folded name matches a published spelling, "
                    "also return other names at or above the 0.6 cutoff. "
                    "By default an exact match is returned alone."
                ),
            ),
        ] = False,
    ) -> SuggestionResponse:
        """Suggest published street spellings and their difflib ratios."""
        return _suggestions(
            service.correct_street(
                street,
                postcode,
                include_neighbours=include_neighbours,
            )
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
        include_neighbours: Annotated[
            bool,
            Query(
                description=(
                    "When the folded name matches a published spelling, "
                    "also return other names at or above the 0.6 cutoff. "
                    "By default an exact match is returned alone."
                ),
            ),
        ] = False,
    ) -> SuggestionResponse:
        """Suggest published city spellings and their difflib ratios."""
        return _suggestions(
            service.correct_city(
                city,
                postcode,
                include_neighbours=include_neighbours,
            )
        )

    return app


def _suggestions(hits: list[Suggestion]) -> SuggestionResponse:
    return SuggestionResponse(
        suggestions=[SuggestionHit(name=hit.name, score=hit.score) for hit in hits]
    )


app = create_app()


def main() -> None:
    """Load the PCS files and serve the API."""
    import uvicorn

    host = os.environ.get("ADDRESS_HOST", "127.0.0.1")
    port = int(os.environ.get("ADDRESS_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
