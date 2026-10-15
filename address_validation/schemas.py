"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ValidateRequest(BaseModel):
    """One address to check against the PCS reference data."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "street": "Smallepad",
                    "house_number": 30,
                    "extension": "E",
                    "postcode": "3811 MG",
                    "city": "AMERSFOORT",
                }
            ]
        },
    )

    street: str = Field(description="Street name, or Postbus / Antwoordnummer.")
    house_number: int | str = Field(
        description='House number. A string may include the extension, as in "30E".',
        examples=[30],
    )
    extension: str | None = Field(
        default=None,
        description=(
            "Optional toevoeging, such as E or bis. Omit it when there is none."
        ),
        examples=["E"],
    )
    postcode: str = Field(
        description="PC6, with or without a space.",
        examples=["3811 MG"],
    )
    city: str = Field(description="City name.", examples=["AMERSFOORT"])


class ValidateLinesRequest(BaseModel):
    """Two postal lines, the shape :meth:`AddressService.validate_lines` reads.

    Blank lines do not count. Any other count than two is rejected here,
    before the reference data is consulted. A pair that cannot be parsed
    is rejected by the service, also as HTTP 422.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"lines": ["Smallepad 30E", "3811 MG  AMERSFOORT"]},
            ]
        },
    )

    lines: list[str] = Field(
        description=(
            "Street line, then postcode and city. Blank lines are ignored. "
            'Example: "Smallepad 30E" and "3811 MG  AMERSFOORT".'
        ),
    )

    @model_validator(mode="after")
    def exactly_two_content_lines(self) -> ValidateLinesRequest:
        content = [line.strip() for line in self.lines if line.strip()]
        if len(content) != 2:
            raise ValueError("exactly two non-blank address lines are required")
        return self


class ValidateResponse(BaseModel):
    """Whether the submitted address occurs in the reference data.

    ``reason`` is ``not_found`` when the input parsed and the address is
    absent. It is omitted when ``valid`` is true. Input the parser rejects
    is HTTP 422 and does not use this body.
    """

    valid: bool
    reason: Literal["not_found"] | None = None


class ExtractFileResponse(BaseModel):
    """SHA-256 and size of one PCS file."""

    name: str
    sha256: str
    size: int


class ReadyResponse(BaseModel):
    """The extract loaded at startup. ``ready`` is true once this body exists."""

    ready: bool
    source: str = Field(
        description='Directory the files were read from, or "repository".',
    )
    postcodes: int
    streets: int
    cities: int
    ranges: int
    files: list[ExtractFileResponse]


class LookupResponse(BaseModel):
    """Formatted address, or an empty list with a reason."""

    lines: list[str] = Field(
        description=(
            "Street line and city line. The city line has two spaces before "
            'the city ("3811 MG  AMERSFOORT"). Empty when the number is '
            "absent or more than one street contains it."
        ),
        examples=[["Smallepad 30E", "3811 MG  AMERSFOORT"]],
    )
    reason: Literal["not_found", "ambiguous"] | None = Field(
        default=None,
        description=(
            "Omitted when lines are present. not_found: the postcode is a "
            "PC6 and no range contains the house number. ambiguous: more "
            "than one street contains it."
        ),
    )


class SuggestionHit(BaseModel):
    """A published spelling and its difflib ratio against the query."""

    name: str = Field(examples=["AMERSFOORT"])
    score: float = Field(
        description=(
            "SequenceMatcher ratio of the folded names. 1 is an exact "
            "folded match. Other hits are at or above 0.6."
        ),
        examples=[0.9473684210526315],
    )


class SuggestionResponse(BaseModel):
    """Ranked, unique suggestions. At most five.

    An exact folded match is returned alone unless the request sets
    ``include_neighbours``.
    """

    suggestions: list[SuggestionHit] = Field(
        description=(
            "Best score first. Each item is the published spelling and "
            "its difflib ratio. An empty query, an unusable postcode, or "
            "no close match is []."
        ),
    )
