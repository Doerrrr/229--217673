FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir rdkit==2025.3.6

WORKDIR /opt/ddi-release
COPY app/ /opt/ddi-curator/
COPY bin/ddi-curate /usr/local/bin/ddi-curate
COPY bin/ddi-release-audit /usr/local/bin/ddi-release-audit
COPY bridge/ /opt/ddi-bridge/
COPY release/ /opt/ddi-release/
COPY data/ /data/

RUN chmod 0755 /usr/local/bin/ddi-curate /usr/local/bin/ddi-release-audit \
    /opt/ddi-curator/curate.py /opt/ddi-bridge/build.sh \
    && mkdir -p /output

CMD ["/bin/bash"]
