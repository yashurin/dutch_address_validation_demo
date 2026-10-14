"""Fuzzy city and street suggestions.

Matching uses :class:`difflib.SequenceMatcher`, the same ratios as
:func:`difflib.get_close_matches`. Comparison is done on names folded by
:func:`address_validation.normalise_name`. The strings returned are the
published spellings, so ``"amsterdm"`` can suggest ``"AMSTERDAM"``.

``get_close_matches`` itself is not called: it would return the folded
string it compared, and the caller needs the published one.

Candidate sets
--------------
A PC6 (``1011AA``) contributes only the names on that postcode. A PC4
(``1011``) contributes the names in that district. Omitting the postcode
scores the whole catalogue.

Cities are about 2,500 names, so an unscoped city query stays in the
milliseconds. Streets are about 138,000 distinct names. Scoring all of
them takes a few hundred milliseconds. A PC4 holds a few dozen streets
on average and a few hundred in the busiest districts. A PC6 usually
holds one or two. Pass a postcode for street correction when you have one.

The first correction builds this index by walking every house-number
range once. Later corrections on the same service reuse it.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from address_validation.models import (
    PO_BOX_STREET,
    REPLY_STREET,
    InMemoryRepository,
    SeriesKind,
)
from address_validation.normalise import normalise_name
from address_validation.postcode import normalise_postcode

# difflib.get_close_matches uses 0.6. Below that, short names that share
# only a few characters start to appear.
SUGGESTION_CUTOFF = 0.6

# The scan still scores every candidate in scope. This only trims the list
# that is returned.
SUGGESTION_LIMIT = 5

_PC4 = re.compile(r"^[1-9][0-9]{3}$")
_Scope = tuple[str, str]


@dataclass(frozen=True, slots=True)
class _NameList:
    """Distinct names, plus where each name occurs.

    ``published[i]`` is the spelling to return. ``normalised[i]`` is what
    difflib compares. ``by_pc4`` lists the indexes that occur in that
    district. ``id_to_index`` maps a street or city id onto ``published``.
    """

    published: tuple[str, ...]
    normalised: tuple[str, ...]
    by_pc4: dict[str, tuple[int, ...]]
    id_to_index: dict[int, int]


@dataclass(frozen=True, slots=True)
class SuggestionIndex:
    """Folded city and street catalogues for one repository."""

    cities: _NameList
    streets: _NameList
    postbus_index: int
    reply_index: int

    @classmethod
    def build(cls, repository: InMemoryRepository) -> SuggestionIndex:
        """Index every distinct city and street name in ``repository``."""
        cities, city_ids = _intern_records(
            (city.city_id, city.name) for city in repository.cities.values()
        )
        streets, street_ids = _intern_records(
            (street.street_id, street.name) for street in repository.streets.values()
        )
        postbus_index = _append(streets, PO_BOX_STREET)
        reply_index = _append(streets, REPLY_STREET)
        city_pc4: dict[str, set[int]] = defaultdict(set)
        street_pc4: dict[str, set[int]] = defaultdict(set)
        for postcode, ranges in repository.ranges_by_postcode.items():
            district = postcode[:4]
            city_bucket = city_pc4[district]
            street_bucket = street_pc4[district]
            for range_ in ranges:
                city_index = city_ids.get(range_.city_id)
                if city_index is not None:
                    city_bucket.add(city_index)
                if range_.kind is SeriesKind.PO_BOX:
                    street_bucket.add(postbus_index)
                elif range_.kind is SeriesKind.REPLY_NUMBER:
                    street_bucket.add(reply_index)
                else:
                    street_index = street_ids.get(range_.street_id)
                    if street_index is not None:
                        street_bucket.add(street_index)
        return cls(
            cities=_freeze(cities, city_pc4, city_ids),
            streets=_freeze(streets, street_pc4, street_ids),
            postbus_index=postbus_index,
            reply_index=reply_index,
        )

    def correct_city(
        self,
        repository: InMemoryRepository,
        city: str,
        postcode: str | None,
    ) -> list[str]:
        """Rank city suggestions. See :meth:`AddressService.correct_city`."""
        return self._correct(repository, self.cities, city, postcode, streets=False)

    def correct_street(
        self,
        repository: InMemoryRepository,
        street: str,
        postcode: str | None,
    ) -> list[str]:
        """Rank street suggestions. See :meth:`AddressService.correct_street`."""
        return self._correct(repository, self.streets, street, postcode, streets=True)

    def _correct(
        self,
        repository: InMemoryRepository,
        names: _NameList,
        query: str,
        postcode: str | None,
        *,
        streets: bool,
    ) -> list[str]:
        scope = _parse_scope(postcode)
        if scope is None:
            return []
        try:
            folded = normalise_name(query)
        except (TypeError, ValueError):
            return []
        indexes = _indexes_in_scope(
            names,
            repository,
            scope,
            postbus_index=self.postbus_index if streets else None,
            reply_index=self.reply_index if streets else None,
        )
        return rank_suggestions(folded, names.normalised, names.published, indexes)


def rank_suggestions(
    folded_query: str,
    normalised: tuple[str, ...],
    published: tuple[str, ...],
    indexes: tuple[int, ...] | None,
    *,
    limit: int = SUGGESTION_LIMIT,
    cutoff: float = SUGGESTION_CUTOFF,
) -> list[str]:
    """Return up to ``limit`` published names, best difflib score first.

    ``indexes is None`` scores every name. Otherwise only those positions
    are scored. A name is kept when ``real_quick_ratio``, ``quick_ratio``
    and ``ratio`` all reach ``cutoff``, which is how
    :func:`difflib.get_close_matches` decides. Equal scores are ordered by
    casefolded published name, then by the published name, so the list
    does not depend on catalogue order.
    """
    if limit < 1:
        return []
    # Cache the query (sequence 2). set_seq1 is the per-candidate call,
    # which is what get_close_matches does and what SequenceMatcher expects
    # when one string is compared with many.
    matcher = difflib.SequenceMatcher()
    matcher.set_seq2(folded_query)
    positions = range(len(published)) if indexes is None else indexes
    scored: list[tuple[float, str]] = []
    for index in positions:
        matcher.set_seq1(normalised[index])
        if matcher.real_quick_ratio() < cutoff or matcher.quick_ratio() < cutoff:
            continue
        score = matcher.ratio()
        if score < cutoff:
            continue
        scored.append((score, published[index]))
    scored.sort(key=lambda item: (-item[0], item[1].casefold(), item[1]))
    unique: list[str] = []
    seen: set[str] = set()
    for _score, name in scored:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
        if len(unique) == limit:
            break
    return unique


def _parse_scope(postcode: str | None) -> _Scope | None:
    """Return ``("all", "")``, ``("pc4", "1011")`` or ``("pc6", "1011AA")``.

    ``None`` is the broad search. Any other value must be a PC4 or a PC6
    after spaces are removed. Anything else is unusable.
    """
    if postcode is None:
        return ("all", "")
    if not isinstance(postcode, str):
        return None
    compact = "".join(postcode.split()).upper()
    if _PC4.fullmatch(compact):
        return ("pc4", compact)
    try:
        return ("pc6", normalise_postcode(compact))
    except (TypeError, ValueError):
        return None


def _indexes_in_scope(
    names: _NameList,
    repository: InMemoryRepository,
    scope: _Scope,
    *,
    postbus_index: int | None,
    reply_index: int | None,
) -> tuple[int, ...] | None:
    kind, value = scope
    if kind == "all":
        return None
    if kind == "pc4":
        return names.by_pc4.get(value, ())
    ranges = repository.ranges_by_postcode.get(value)
    if not ranges:
        return ()
    found: list[int] = []
    seen: set[int] = set()
    for range_ in ranges:
        index = _range_index(
            names,
            range_.kind,
            range_.city_id,
            range_.street_id,
            postbus_index,
            reply_index,
        )
        if index is None or index in seen:
            continue
        seen.add(index)
        found.append(index)
    return tuple(found)


def _range_index(
    names: _NameList,
    kind: SeriesKind,
    city_id: int,
    street_id: int,
    postbus_index: int | None,
    reply_index: int | None,
) -> int | None:
    if postbus_index is None:
        return names.id_to_index.get(city_id)
    if kind is SeriesKind.PO_BOX:
        return postbus_index
    if kind is SeriesKind.REPLY_NUMBER:
        return reply_index
    return names.id_to_index.get(street_id)


def _intern_records(
    records: Iterable[tuple[int, str]],
) -> tuple[list[str], dict[int, int]]:
    published: list[str] = []
    by_id: dict[int, int] = {}
    name_to_index: dict[str, int] = {}
    for record_id, name in records:
        index = name_to_index.get(name)
        if index is None:
            index = len(published)
            name_to_index[name] = index
            published.append(name)
        by_id[record_id] = index
    return published, by_id


def _append(published: list[str], name: str) -> int:
    """Add ``name`` unless that spelling is already in ``published``."""
    try:
        return published.index(name)
    except ValueError:
        published.append(name)
        return len(published) - 1


def _freeze(
    published: list[str],
    by_pc4: dict[str, set[int]],
    id_to_index: dict[int, int],
) -> _NameList:
    normalised = tuple(normalise_name(name) for name in published)
    return _NameList(
        published=tuple(published),
        normalised=normalised,
        by_pc4={key: tuple(sorted(indexes)) for key, indexes in by_pc4.items()},
        id_to_index=id_to_index,
    )
