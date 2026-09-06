# This build stage compiles dependencies that do not publish Python 3.13 wheels.
FROM python:3.13-slim AS dependency-builder
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY warehouse/requirements.txt /tmp/requirements-dbt.txt
RUN pip wheel --no-cache-dir --wheel-dir /tmp/wheels \
    -r /tmp/requirements-dbt.txt

# This final image runs dbt and does not retain the compiler.
FROM python:3.13-slim
WORKDIR /usr/app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dependency-builder /tmp/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/* \
    && rm -rf /tmp/wheels

ENTRYPOINT ["dbt"]
CMD ["--help"]
