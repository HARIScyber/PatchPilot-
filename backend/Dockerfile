FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
ARG RENDER_GIT_COMMIT=unknown
ARG RENDER_GIT_BRANCH=unknown
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/database \
    && chown appuser:appuser /app/database
COPY app ./app
ENV APP_COMMIT_SHA=${RENDER_GIT_COMMIT} \
    APP_GIT_BRANCH=${RENDER_GIT_BRANCH}
RUN python -c 'import datetime,json,os; json.dump({"commit":os.getenv("APP_COMMIT_SHA","unknown"),"branch":os.getenv("APP_GIT_BRANCH","unknown"),"build_date":datetime.datetime.now(datetime.timezone.utc).isoformat()},open("/app/app/version.json","w"))'
USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
