FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
WORKDIR /app
RUN --mount=type=tmpfs,target=/var/cache/apt/archives apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY ml/requirements.txt /tmp/ml-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/ml-requirements.txt
COPY ml/ ml/
COPY services/__init__.py services/
COPY services/forecast/ services/forecast/
ENTRYPOINT ["python", "-m", "ml.job"]
