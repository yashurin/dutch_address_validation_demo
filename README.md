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


## Choices relative to the assignment

The five routines suggested for the implementation are snake_case methods on `AddressService`.

| Brief | This code |
| --- | --- |
| `lookupAddress` | `AddressService.lookup_address` |
| `validate` | `AddressService.validate` |
| `validateLines` | `AddressService.validate_lines` |
| `correctCity` | `AddressService.correct_city` |
| `correctStreet` | `AddressService.correct_street` |

The code is a package (`models`, `loader`,
`service`, `suggest`, `api`) so loading, matching, and the HTTP layer stay
separate for better readability and maintainability. `AddressService` is the entry point for the five routines.

Lookup accepts one string, with the two lines separated by a
newline or a semicolon. `lookup_address` returns a `LookupResult`: the
street line and the city line, or no lines together with `not_found` or
`ambiguous`. The API returns that pair as
`lines`.

`validate` and `validate_lines` return true or false once the address has
parsed. Input the parser rejects raises `InvalidAddress`. The API returns
HTTP 422 for that error and `{"valid": false, "reason": "not_found"}` for
a parsed miss.

The suggested house number is an `int`, and the extension is a required
`str`. Here the house number may also be a string such as `"30E"`, and the
extension may be omitted. Many addresses have no toevoeging.

`correct_city` and `correct_street` are described as a list of names. They
return `Suggestion` values: the published spelling and the difflib ratio.
An exact match on the lowercased name is returned alone.
`include_neighbours` adds the other names at or above 0.6, at most five in
total. A partial name yields candidate street or city names. It
does not expand into formatted postal addresses. The suggested routines
stop at the names, and this program stays with those five operations.

Street and city text on a result is the spelling stored in the PCS files.
The sample box writes `Amersfoort`. `PCS_WPL.dat` stores `AMERSFOORT`.

The validation path does not import FastAPI. FastAPI and Uvicorn implement
the optional JSON API. There is no DB. A lookup reads the ranges of one postcode from memory.


## Development environment

Python 3.13 or newer with the standard library. The API
adds FastAPI and Uvicorn. Tests add pytest and httpx. Black and Ruff are the
formatter and the linter (line length 88; Ruff selects E, F, I, UP, B and ANN).

After the files are
on disk, lookup and validation run locally. Startup hashes each file and
builds the street and city suggestion index before the process accepts
connections.

Place the three files in `data/` under these names. Start commands from the
repository root, or set `ADDRESS_DATA_DIR` to that directory.

## Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`pip install -e .` is enough to run the API. The `dev` extra adds pytest,
httpx, Black, and Ruff. 

```bash
address-validation-api
```

The same server is `python -m address_validation`, or:

```bash
uvicorn address_validation.api:app --host 127.0.0.1 --port 8000
```

Startup reads the three files, records a SHA-256 of each, and builds the
suggestion index before the process accepts connections. That takes a
couple of seconds. `GET /api/v1/ready` then reports the loaded counts and
those hashes. `ADDRESS_HOST` and `ADDRESS_PORT` change the bind address
(`127.0.0.1:8000` by default). Interactive docs are at
<http://127.0.0.1:8000/docs>.

`create_app(repository)` builds an app around an existing
`InMemoryRepository` and does not read the files. The unit tests use that
path. The functional tests and `address-validation-api` load `data/`.

## API examples

Lookup `3811 MG`, house number `30`, extension `E`. The city line has two
spaces before the city. A postcode that parses but does not contain the
number returns `{"lines": [], "reason": "not_found"}`. The same number on
more than one street returns `"reason": "ambiguous"` and no lines. A
postcode, house number, or extension the parser rejects is HTTP 422.

```bash
curl -sG "http://127.0.0.1:8000/api/v1/lookup" \
  --data-urlencode "postcode=3811 MG" \
  --data-urlencode "house_number=30" \
  --data-urlencode "extension=E"
```

```json
{"lines":["Smallepad 30E","3811 MG  AMERSFOORT"]}
```

Validate the same address. A parsed address that is not in the extract
returns `{"valid": false, "reason": "not_found"}`. A bad postcode, an
empty name, or a malformed extension is HTTP 422, as is a missing JSON
field.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/validate" \
  -H "Content-Type: application/json" \
  -d '{"street":"Smallepad","house_number":30,"extension":"E","postcode":"3811 MG","city":"AMERSFOORT"}'
```

```json
{"valid":true}
```

The same check accepts the two postal lines. Blank lines are ignored.
Exactly two remaining lines are required, and a line that does not parse
is HTTP 422. A pair that parses but is not in the extract returns
`{"valid": false, "reason": "not_found"}`.

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/validate/lines" \
  -H "Content-Type: application/json" \
  -d '{"lines":["Smallepad 30E","3811 MG  AMERSFOORT"]}'
```

```json
{"valid":true}
```

`GET /api/v1/ready` is the startup record: `ready`, the data directory,
postcode / street / city / range counts, and for each of `PCS_HNR.dat`,
`PCS_STR.dat`, and `PCS_WPL.dat` the file name, byte size, and SHA-256.
When the process was given an in-memory repository instead of a directory,
`files` is empty and `source` is `repository`.

Suggest a street. Each hit is the published spelling and the difflib
ratio of the folded names. `postcode` may be a PC6 (`3811 MG`) or a PC4
(`3811`). Leave it out to search every street; that call takes a few
hundred milliseconds.

```bash
curl -sG "http://127.0.0.1:8000/api/v1/correct/street" \
  --data-urlencode "street=smallepd" \
  --data-urlencode "postcode=3811 MG"
```

```json
{"suggestions":[{"name":"Smallepad","score":0.9411764705882353}]}
```

Suggest a city. Omitting `postcode` searches the whole city list, which
stays in the milliseconds. An exact folded match is returned alone, with
score 1. `include_neighbours=true` also returns other names at or above
0.6, still at most five and with the exact match first. `ROTTERDAM` scores
about 0.67 against `Amsterdam`, so it appears when the catalogue is small
enough; on the full city list closer names take the remaining slots.

```bash
curl -sG "http://127.0.0.1:8000/api/v1/correct/city" \
  --data-urlencode "city=amersfort" \
  --data-urlencode "postcode=3811"
```

```json
{"suggestions":[{"name":"AMERSFOORT","score":0.9473684210526315}]}
```

## Algorithm and data structures

The loader streams the three files into one
`InMemoryRepository`:

- `ranges_by_postcode` maps a normalised PC6 (`"1011 AA"` becomes
  `"1011AA"`) to a tuple of `HouseNumberRange` rows. A lookup always
  starts from one postcode, and that postcode has only a few ranges, so
  the tuple is scanned linearly. Each range stores street and city ids.
  About 629,000 ranges share about 138,000 street names and 2,500 city
  names instead of repeating the strings. The map is a read-only proxy.
  `ranges_for` returns the stored tuple.
- `streets` maps a street id to one frozen `Street` record (the published
  name). Street id 0 is absent: a postbus or antwoordnummer has no street
  in the file.
- `cities` maps a city id to one frozen `City`. Names stay as published,
  cities in uppercase (`AMSTERDAM`, `'S-GRAVENHAGE`).

`HouseNumberRange`, `Street`, and `City` are frozen slotted dataclasses.
The street and city maps are read-only as well. Nothing in the repository
can be appended or replaced after load.

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
empty extension is omitted. Lookup returns the two postal lines when one
street contains the number. A PC6 that does not contain it is `not_found`.
The same number on more than one street is `ambiguous`, and the lines are
not guessed. A postcode, house number, extension, or name the parser
rejects raises `InvalidAddress`; the API turns that into HTTP 422. Validate
uses the same split: false, with reason `not_found`, means the input parsed
and the address is not in the extract. When several streets contain the
number, a supplied street and city that match one of them is valid.

Suggestions compare `normalise_name` forms with `difflib.SequenceMatcher`
and return the published spelling together with that ratio. The query is
cached on the matcher, then each candidate is rejected with
`real_quick_ratio` and `quick_ratio` before `ratio` is computed. The cutoff
is 0.6 and at most five names are returned, best score first. An exact
folded match is returned alone. `include_neighbours` puts the other names
above the cutoff back in the list, exact match first. Equal scores are
ordered by lowercased name, then by the published name. A PC6 limits the
candidates to that postcode. A PC4 limits them to that district. The index
is built when the service is created, which for the API is during startup,
before the port accepts connections. With no postcode every distinct city
or street is scored. City search is a few milliseconds. Street search is a
few hundred milliseconds, which is why a postcode should be passed when one
is known. `Postbus` and `Antwoordnummer` are suggested where those series
occur, and on every unscoped street search. An empty correction query or an
unusable postcode still returns an empty list: those calls are searches,
not address checks.

## Testing

Unit tests call the library in-process. Many of them build a handful of
ranges in memory. The tests that need the PCS files share one session
load. Functional tests start `python -m address_validation` on a free
localhost port, wait until `/api/v1/ready` reports the extract, and send
HTTP requests for real addresses (Smallepad 30E in Amersfoort, De
Ruyterkade Steigers 7 in Amsterdam, Postbus 25, the two-line form, and the
suggestion lists for `smallepd` and `amersfort`). The process is stopped
when the session ends.

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
`dev` (or `test`) extra, because they use HTTP. The unscoped street
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

Startup again reads the files, hashes them, and builds the suggestion
index before the port accepts connections. The curl examples above then
work at `http://127.0.0.1:8000`. `ADDRESS_DATA_DIR` in the image is
`/app/data`, which is the `source` field of `/api/v1/ready`.

## Assumptions

The loader accepts the three PCS files as they are published: tilde
separated, space padded, UTF-8. Kind, parity, and street id stay in
the combinations that extract uses. A street or postbus row that breaks
those combinations is rejected. A PC6 is treated as having one city. The
current files have that shape. The loader does not check it. 

When one
house number would produce two street or city labels, lookup reports
`ambiguous` and does not choose. In this extract that overlap was not
found. Validate still accepts the address when the supplied street and
city match one of the labels.

Odd, even, and doorlopend ranges contain every second integer from the
start. Doorlopend numbering is stored as one odd row and one even row, so
`D` is not "every integer". A blank parity matches every integer in the
span. Parity `G` is only the span 0–0. House number 0 means the street
has no number. House numbers run from 0 through 99999. 

Each postcode holds few ranges, so those tuples are scanned linearly.
Street and city strings are stored once and
referenced by id. After load, the maps are read-only and each postcode's
ranges are a tuple.

Name comparison lowercases, collapses whitespace, and maps `` ` ``, `'`,
and the curly apostrophes to `'`. Other punctuation stays. `ij` and `y`
are not treated as the same letter, and abbreviations are not expanded.
`lower()` matches `casefold()` on the ASCII names in this extract. A
caller who types `ß` does not match a name stored as `ss`. The text
returned to the caller is the spelling in the file. A street suffix
` AB` is part of the name.

The files do not list toevoegingen. Any well-formed extension is accepted
and is not checked against the building. A single letter is uppercased
and glued on. A longer token is lowercased and hyphenated, at most 8
characters, letters, digits, and internal hyphens. On a numberless address
the extension is accepted by validate and left off the printed line. In
the two-line form, the last number on the street line is the house number,
so `Laan 1945 10` keeps `Laan 1945` as the street. The city line parses
with any whitespace after the postcode. Formatting writes two spaces.

Suggestions use a difflib ratio of at least 0.6 and return at most five
names. Equal scores are ordered by the lowercased published name, then by
the published name. For correction, a PC4 is exactly four digits with a
first digit other than 0. Anything else must be a PC6. Only `postcode`
omitted entirely searches the whole catalogue. An empty postcode is an
unusable scope and returns no suggestions. An empty name does the same.
`Postbus` and `Antwoordnummer` are synthetic street names: they appear on
every unscoped street search, and inside a PC4 or PC6 only when that scope
contains the series. Two street ids that share a published name produce
one suggestion.

One `AddressService` lives for the life of the process. Replacing the
files on disk does nothing until restart. Lookup and validate are reads
of one postcode. 

Unscoped street correction scores the whole street
catalogue and is the expensive call. The endpoints are synchronous. There
is no authentication and no quota. 

Tests that name real addresses, top
suggestion lists, and row counts are pinned to this PCS drop. A newer
drop can fail those tests without a change in the matching rules.

Validate and the two correction calls stay on different HTTP shapes.
Validate submits an address document, so it is a JSON body. Lookup,
correction, and readiness are reads of a few fields, so they stay query
parameters.

## Further improvements

The five routines return a
verdict, two postal lines, or candidate names. A search that turned
`Smalle` in `3811` into postal lines would be a new operation.

Restart still parses the text files. A compact snapshot, loaded into the
same PC6 dictionary, would shorten startup. A database is useful there.

Reload without a restart means building a second repository and swapping
it onto the app when the snapshot changes. In-flight requests would keep
the previous service. The maps are already frozen, so a request cannot
see a half-built table.

Running it as a service would add a network policy or authentication, a
limit on unscoped street correction, and logs for load time and correction time. 

Batch
validate, many addresses in one request against the same repository, is
the usual next call for a postal pipeline.
