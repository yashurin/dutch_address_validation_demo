"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class ValidateResponse(BaseModel):
    """Whether the submitted address occurs in the reference data."""

    valid: bool


class LookupResponse(BaseModel):
    """Formatted address, or an empty list when it is not in the data."""

    lines: list[str] = Field(
        description=(
            "Street line and city line. The city line has two spaces before "
            'the city ("3811 MG  AMERSFOORT"). Empty when the postcode and '
            "house number are unknown, the extension is malformed, or more "
            "than one street contains that number."
        ),
        examples=[["Smallepad 30E", "3811 MG  AMERSFOORT"]],
    )


class SuggestionResponse(BaseModel):
    """Ranked, unique published spellings. At most five."""

    suggestions: list[str] = Field(
        description=(
            "Best match first. Names at or above the difflib cutoff of 0.6. "
            "An empty query, an unusable postcode, or no close match is []."
        ),
    )
