FROM python:3.11-slim-bookworm

RUN python -m pip install --no-cache-dir rdkit==2025.3.6 ortools==9.14.6206 scipy==1.15.3

WORKDIR /opt/ddi-release

COPY app/release.py /opt/ddi-release/release.py
COPY bin/ddi-release /usr/local/bin/ddi-release
COPY data/ /data/

RUN chmod 0755 /usr/local/bin/ddi-release /opt/ddi-release/release.py \
    && mkdir -p /output

CMD ["/bin/bash"]
