FROM python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir pytest==9.1.1 PyYAML==6.0.3
RUN useradd --uid 1000 --create-home bench && mkdir /testbed /workflow /grade && chown bench:bench /testbed /workflow /grade
USER bench
WORKDIR /testbed
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/testbed
CMD ["sleep", "infinity"]
