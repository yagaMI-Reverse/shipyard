# DocuChat FastAPI backend — image built for the Kubernetes deploy.
#
# Differences from the original single-host image:
#   * runs as an unprivileged user (the chart enforces runAsNonRoot)
#   * version baked in at build time and reported in the JSON logs
#   * uvicorn access log off — k8s_runtime.py emits structured logs instead
#
# Python is pinned to 3.12 so scikit-learn/numpy install from prebuilt wheels
# (no compiler needed).
FROM python:3.12-slim

# Build metadata (CI passes the git SHA).
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Unprivileged runtime user; nothing under /app needs to be writable.
RUN useradd --system --uid 10001 --no-create-home appuser \
    && chown -R appuser:appuser /app
USER 10001

EXPOSE 8000

# UVICORN_WORKERS lets the chart trade CPU per pod against replica count.
# One worker per pod keeps the HPA's CPU signal clean and interpretable.
ENV UVICORN_WORKERS=1
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS} --no-access-log"]
