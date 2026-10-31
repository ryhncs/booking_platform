FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
# Optional PyPI mirror for networks where pypi.org / files.pythonhosted.org
# are unreachable. Set PIP_INDEX_URL in the repo-root .env to use one.
ARG PIP_INDEX_URL=""
RUN REQS=requirements.txt; [ "$INSTALL_DEV" = "true" ] && REQS=requirements-dev.txt; \
    pip install --retries 10 --timeout 60 \
        ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} -r "$REQS"

COPY . .

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
