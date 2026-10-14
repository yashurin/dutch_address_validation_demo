# Dutch address validation

In-memory validation of Dutch addresses against the PCS files in `data/`
(`PCS_HNR.dat`, `PCS_STR.dat`, `PCS_WPL.dat`). A small HTTP API loads those
files once at startup and serves the repository from memory.

```
address_validation/    library and FastAPI application
data/                  the three PCS files
tests/unit/            in-process tests
tests/functional/      tests that start the API
pyproject.toml
Dockerfile
```

The data files are part of this tree. They are not packed into the wheel.
An archive of the project needs `address_validation/`, `data/`, `tests/`,
`pyproject.toml`, `README.md`, `Dockerfile`, and `.dockerignore`. Leave out
`.venv/`, `__pycache__/`, and `.pytest_cache/`.

## Development environment

Python 3.13 or newer. The library itself uses the standard library. The API
adds FastAPI and Uvicorn. Tests add pytest and httpx. Black and Ruff are the
formatter and the linter (line length 88; Ruff selects E, F, I, UP, and B).

No database and no network call to an address service. After the files are
on disk, lookup and validation run locally. The first city or street
correction builds a name index in the process; later corrections reuse it.

Place the three files in `data/` under these names. Start commands from the
repository root, or set `ADDRESS_DATA_DIR` to that directory.

## Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`pip install -e .` is enough to run the API. The `dev` extra adds pytest,
httpx, Black, and Ruff. On Windows the activate script is
`.venv\Scripts\activate`.

```bash
address-validation-api
```

The same server is `python -m address_validation`, or:

```bash
uvicorn address_validation.api:app --host 127.0.0.1 --port 8000
```

Startup reads the three files before the process accepts connections. That
takes a couple of seconds. `ADDRESS_HOST` and `ADDRESS_PORT` change the bind
address (`127.0.0.1:8000` by default). Interactive docs are at
<http://127.0.0.1:8000/docs>.

`create_app(repository)` builds an app around an existing
`InMemoryRepository` and does not read the files. The unit tests use that
path. The functional tests and `address-validation-api` load `data/`.

## API examples

Lookup `3811 MG`, house number `30`, extension `E`. The city line has two
spaces before the city. An unknown address returns `{"lines": []}`.

```bash
curl -sG "http://127.0.0.1:8000/api/v1/lookup" \
  --data-urlencode "postcode=3811 MG" \
  --data-urlencode "house_number=30" \
  --data-urlencode "extension=E"
```

```json
{"lines":["Smallepad 30E","3811 MG  AMERSFOORT"]}
```

Validate the same address. A miss, including a bad postcode or an empty
field, returns `{"valid": false}`. A missing JSON field is HTTP 422.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/validate" \
  -H "Content-Type: application/json" \
  -d '{"street":"Smallepad","house_number":30,"extension":"E","postcode":"3811 MG","city":"AMERSFOORT"}'
```

```json
{"valid":true}
```

Suggest a street. `postcode` may be a PC6 (`3811 MG`) or a PC4 (`3811`).
Leave it out to search every street; that call takes a few hundred
milliseconds.

```bash
curl -sG "http://127.0.0.1:8000/api/v1/correct/street" \
  --data-urlencode "street=smallepd" \
  --data-urlencode "postcode=3811 MG"
```

```json
{"suggestions":["Smallepad"]}
```

Suggest a city. Omitting `postcode` searches the whole city list, which
stays in the milliseconds.

```bash
curl -sG "http://127.0.0.1:8000/api/v1/correct/city" \
  --data-urlencode "city=amersfort" \
  --data-urlencode "postcode=3811"
```

```json
{"suggestions":["AMERSFOORT"]}
```

## Algorithm and data structures

The loader streams the three tilde-separated files into one
`InMemoryRepository`:

- `ranges_by_postcode` maps a normalised PC6 (`"1011 AA"` becomes
  `"1011AA"`) to a short list of `HouseNumberRange` rows. A lookup always
  starts from one postcode, and that postcode has only a few ranges, so
  the list is scanned linearly. Each range stores street and city ids.
  About 629,000 ranges share about 138,000 street names and 2,500 city
  names instead of repeating the strings.
- `streets` maps a street id to one frozen `Street` record (the published
  name). Street id 0 is absent: a postbus or antwoordnummer has no street
  in the file.
- `cities` maps a city id to one frozen `City`. Names stay as published,
  cities in uppercase (`AMSTERDAM`, `'S-GRAVENHAGE`).

`HouseNumberRange`, `Street`, and `City` are frozen slotted dataclasses.
The repository is built once and then treated as read-only.

A range matches a house number as follows. Odd (`O`), even (`E`), and
doorlopend (`D`) ranges step by two from `from_number`, and both ends share
that parity. Doorlopend numbering is still stored as one odd row and one
even row, so `1011 MR` contains 2 and does not contain 19. A blank parity
matches every integer in the span; that is how postbus and antwoordnummer
rows are written. A no-number row (`G`) is only `0`–`0` and is printed as
the street name alone. Those streets often keep an ` AB` suffix; the suffix
stays, because the same road can exist again without it.

Postcodes lose their spaces and are uppercased. A PC6 is one digit from
1–9, three more digits, and two letters. Street and city comparison folds
case, collapses whitespace, and treats curly apostrophes as `'`. Extensions
are not in the files. A well-formed toevoeging is accepted and printed: one
letter is glued on (`30E`), a longer token is hyphenated (`30-bis`). An
empty extension is omitted. Lookup returns the two postal lines, or `[]`
when the number is absent, the extension is malformed, or more than one
street contains that number. Validate returns true when the supplied street
and city match any of those rows.

Suggestions compare `normalise_name` forms with `difflib.SequenceMatcher`
and return the published spelling. The query is cached on the matcher, then
each candidate is rejected with `real_quick_ratio` and `quick_ratio` before
`ratio` is computed. The cutoff is 0.6 and at most five names are returned,
best score first. Equal scores are ordered by casefolded name, then by the
published name. A PC6 limits the candidates to that postcode. A PC4 limits
them to that district, through an index built on the first correction. With
no postcode every distinct city or street is scored. City search is a few
milliseconds. Street search is a few hundred milliseconds, which is why a
postcode should be passed when one is known. `Postbus` and `Antwoordnummer`
are suggested where those series occur, and on every unscoped street search.

## Testing

Unit tests call the library in-process. Many of them build a handful of
ranges in memory. The tests that need the PCS files share one session
load. Functional tests start `python -m address_validation` on a free
localhost port, wait until `/openapi.json` answers, and send HTTP requests
for real addresses (Smallepad 30E in Amersfoort, De Ruyterkade Steigers 7
in Amsterdam, Postbus 25, and the suggestion lists for `smallepd` and
`amersfort`). The process is stopped when the session ends.

From the activated virtualenv, at the repository root:

```bash
pytest tests/unit
pytest tests/functional
```

The same split by marker:

```bash
pytest -m unit
pytest -m functional
```

`pytest` with no arguments runs both. Functional tests need `data/` and the
`dev` (or `test`) extra, because they speak HTTP. The unscoped street
suggestion runs once in that session.

```bash
black address_validation tests
ruff check address_validation tests
```

## Docker

The image is Python 3.13. It installs the package and copies `data/` to
`/app/data`. Inside the container the server listens on `0.0.0.0:8000`.

```bash
docker build -t address-validation .
docker run --rm -p 8000:8000 address-validation
```

Startup again reads the files before the port accepts connections. The curl
examples above then work at `http://127.0.0.1:8000`. `ADDRESS_DATA_DIR` in
the image is `/app/data`.
