FROM python:3.11.17-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
ENV LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir numpy==2.2.6 scipy==1.15.3 ortools==9.14.6206
WORKDIR /work/ramsey
COPY app/ app/
COPY bin/ bin/
COPY packet/ packet/
RUN chmod 755 bin/* && python3 -m compileall -q app
CMD ["bash"]
