FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY address_validation ./address_validation
COPY data ./data

RUN pip install --no-cache-dir .

ENV ADDRESS_HOST=0.0.0.0 \
    ADDRESS_PORT=8000 \
    ADDRESS_DATA_DIR=/app/data

EXPOSE 8000

CMD ["address-validation-api"]
