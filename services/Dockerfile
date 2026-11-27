# syntax=docker/dockerfile:1.14@sha256:4c68376a702446fc3c79af22de146a148bc3367e73c25a5803d453b6b3f722fb
FROM public.ecr.aws/lambda/python:3.12@sha256:ad2f55fe2cf91a997bc986410cab85a41b7c7bae65ba881e69173a76d022133e AS python
COPY services/forecast/requirements.txt /tmp/requirements.txt
COPY services/passengers/preview-requirements.txt /tmp/preview-requirements.txt
RUN python -m pip install --no-cache-dir --no-compile --only-binary=:all: --require-hashes \
    --target "${LAMBDA_TASK_ROOT}" -r /tmp/requirements.txt -r /tmp/preview-requirements.txt
COPY services/ ${LAMBDA_TASK_ROOT}/services/
COPY grid/ ${LAMBDA_TASK_ROOT}/grid/
RUN chmod 0755 "${LAMBDA_TASK_ROOT}" && chmod -R u=rwX,go=rX "${LAMBDA_TASK_ROOT}/services" "${LAMBDA_TASK_ROOT}/grid"
CMD ["services.forecast.handler.handler"]

FROM public.ecr.aws/lambda/nodejs:24@sha256:5f161369102f24d3b088ca52e8e83eeee55e701080ee91af858b4cb2f762b6ef AS push
COPY --chmod=0644 services/delivery/package*.json ${LAMBDA_TASK_ROOT}/
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund && npm cache clean --force
COPY --chmod=0644 services/delivery/index.mjs services/delivery/turbulence.json ${LAMBDA_TASK_ROOT}/
CMD ["index.handler"]
