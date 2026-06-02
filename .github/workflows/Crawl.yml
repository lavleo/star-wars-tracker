# .devcontainer/Dockerfile
FROM mcr.microsoft.com/devcontainers/base:ubuntu

RUN apt-get update && apt-get install -y \
    build-essential \
    libcurl4-openssl-dev \
    libgumbo-dev \
    libsqlite3-dev \
    libcjson-dev \
    sqlite3 \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install flask flask-limiter apscheduler --break-system-packages