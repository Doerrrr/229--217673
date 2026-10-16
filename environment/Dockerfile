FROM python:3.11.17-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce AS tools
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN mkdir /build && curl -fL --retry 2 https://codeload.github.com/arminbiere/cadical/tar.gz/f13d74439a5b5c963ac5b02d05ce93a8098018b8 | tar -xz -C /build && cd /build/cadical-* && ./configure && make -j2 && cp build/cadical /usr/local/bin/cadical
RUN curl -fL --retry 2 https://codeload.github.com/marijnheule/drat-trim/tar.gz/2e3b2dc0ecf938addbd779d42877b6ed69d9a985 | tar -xz -C /build && cd /build/drat-trim-* && gcc -D_DEFAULT_SOURCE -std=c99 -O2 drat-trim.c -o /usr/local/bin/drat-trim
FROM python:3.11.17-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 util-linux build-essential && rm -rf /var/lib/apt/lists/*
COPY --from=tools /usr/local/bin/cadical /usr/local/bin/cadical
COPY --from=tools /usr/local/bin/drat-trim /usr/local/bin/drat-trim
COPY lib/ /opt/phase-codec/
ENV PYTHONPATH=/opt/phase-codec PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8
WORKDIR /work/phase
COPY app/ app/
COPY bin/ bin/
COPY packet/ packet/
COPY clients/ clients/
RUN chmod 755 bin/* && ln -s /work/phase/bin/phase-lab /usr/local/bin/phase-lab && python3 -m compileall -q app /opt/phase-codec
CMD ["bash"]
