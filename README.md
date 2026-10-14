# Dutch address validation

In-memory validation of Dutch addresses against the PCS files in `data/`
(`PCS_HNR.dat`, `PCS_STR.dat`, `PCS_WPL.dat`). The HTTP API loads those
files once at startup and keeps the repository in memory.

Python 3.13 or newer.

## Install

From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`pip install -e .` is enough to run the API. The `dev` extra adds pytest,
Black, and Ruff.

The data files stay in `data/` and are not copied into the wheel. Start
the server from the repository root, or set `ADDRESS_DATA_DIR` to that
directory.

## Run the API

```bash
address-validation-api
```

The same server is `python -m address_validation`, or:

```bash
uvicorn address_validation.api:app --host 127.0.0.1 --port 8000
```

Startup reads the three files before the process accepts connections.
`ADDRESS_HOST` and `ADDRESS_PORT` change the bind address. Interactive
docs are at <http://127.0.0.1:8000/docs>.

`create_app(repository)` builds an app around an existing
`InMemoryRepository` and does not read the files.

## Examples

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
field, returns `{"valid": false}`.

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

## Development

```bash
pytest
black address_validation tests
ruff check address_validation tests
```
