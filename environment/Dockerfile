FROM python:3.11.17-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends gcc make libc6-dev bzip2 zlib1g-dev libbz2-dev liblzma-dev util-linux && apt-get clean
COPY upstream/bcftools-1.20.tar.bz2 /tmp/bcftools-1.20.tar.bz2
RUN mkdir -p /work && tar -xjf /tmp/bcftools-1.20.tar.bz2 -C /work && cd /work/bcftools-1.20 && ./configure --disable-libcurl && make -j2
ENV PATH="/work/bcftools-1.20:/usr/local/bin:/usr/bin:/bin"
COPY Makefile /work/cohort-release/Makefile
COPY src/ /work/cohort-release/src/
COPY packet/ /packet/
WORKDIR /work/cohort-release
RUN make
