FROM python:3.11.17-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
ENV LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
WORKDIR /work/bench
COPY app/ app/
COPY bin/ bin/
COPY packet/ packet/
RUN chmod 755 bin/analyze && python3 -m compileall -q app
CMD ["bash"]
