FROM python:3.11-slim-bookworm

RUN python -m pip install --no-cache-dir rdkit==2025.3.6

WORKDIR /opt/ddi-ledger
COPY app/ /opt/ddi-ledger/
COPY bin/ddi-ledger /usr/local/bin/ddi-ledger
COPY data/ /data/
RUN chmod 0755 /usr/local/bin/ddi-ledger && mkdir -p /state /logs/verifier

CMD ["/bin/bash"]
