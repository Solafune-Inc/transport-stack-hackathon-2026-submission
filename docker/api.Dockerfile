# API server (src/api/main.py): GTFS network + crowding model tables + live GTFS-RT feed.
# The raw GTFS is not in the image; docker-compose.yml mounts it read-only.

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    MPLBACKEND=Agg
WORKDIR /app

# Pick up Debian security fixes released after the base image was built
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

COPY src/ src/
COPY data/eticketing/ data/eticketing/
# crowding.py creates notebooks/figures and reports on import, so they must exist and be writable
RUN gunzip data/eticketing/*.csv.gz \
 && mkdir -p data/delhi_buses_static_gtfs notebooks/figures reports \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && chown app notebooks/figures reports
COPY --chmod=755 docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh

USER app
EXPOSE 8787
ENTRYPOINT ["api-entrypoint.sh"]


# Python tests: docker compose --profile test run --rm tests
FROM runtime AS test
USER root
RUN pip install pytest==9.2.0
COPY pytest.ini .
COPY tests/ tests/
USER app
ENTRYPOINT []
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
