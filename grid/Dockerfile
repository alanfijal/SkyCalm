FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY grid/requirements.txt /tmp/grid-requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/grid-requirements.txt \
    && python -m eccodes selfcheck
RUN --mount=type=tmpfs,target=/var/cache/apt/archives apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY ml/inference-requirements.txt /tmp/inference-requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/inference-requirements.txt
COPY ml/__init__.py ml/artifact.py ml/features.py ml/
COPY grid/ grid/
COPY services/ services/
USER 65532:65532
ENTRYPOINT ["python", "-m", "grid.build"]
CMD ["--aws"]
