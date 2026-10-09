FROM python:3.11-slim-bookworm

RUN python -m pip install --no-cache-dir rdkit==2025.3.6

WORKDIR /opt/ddi-curator

COPY app/ /opt/ddi-curator/
COPY bin/ddi-curate /usr/local/bin/ddi-curate
COPY data/ /data/

RUN chmod 0755 /usr/local/bin/ddi-curate /opt/ddi-curator/curate.py \
    && mkdir -p /output

CMD ["/bin/bash"]
