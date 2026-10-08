FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/

RUN pip install --no-cache-dir uv
RUN uv pip install --system "./apps/api[postgres]"
RUN uv pip install --system ./apps/worker

CMD ["landcrm-worker"]
