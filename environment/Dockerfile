FROM python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y vim curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install numpy scipy matplotlib

RUN mkdir -p /app /logs/verifier

COPY buggy_simulation.py /app/simulation.py

WORKDIR /app
CMD ["/bin/bash"]