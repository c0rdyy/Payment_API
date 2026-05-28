# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 mock \
    && useradd --system --uid 1001 --gid mock --home-dir /app --shell /sbin/nologin mock

WORKDIR /app

RUN pip install --no-cache-dir \
        "fastapi==0.136.1" \
        "uvicorn[standard]==0.47.0" \
        "pydantic==2.13.4"

COPY --chown=mock:mock mock_provider ./mock_provider

USER mock

EXPOSE 9000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:9000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "mock_provider.app:app", "--host", "0.0.0.0", "--port", "9000"]
