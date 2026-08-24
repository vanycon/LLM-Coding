FROM mcr.microsoft.com/devcontainers/rust:1-1-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libsqlite3-dev \
        pkg-config \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*
