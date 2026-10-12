FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends g++
RUN pip install --no-cache-dir rdkit==2025.3.6
WORKDIR /opt/ddi-snapshot
COPY include/ ./include/
COPY src/ ./src/
COPY build.sh client.py ./
COPY data/ /data/
RUN chmod 0755 build.sh && ./build.sh
