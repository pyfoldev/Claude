FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 CHAT_HELPER_CACHE=/tmp/chat-helper
CMD ["python", "bot.pyz"]
COPY requirements.lock ./
# Optional CA bundle for builds behind a TLS proxy; certificate checks stay enabled.
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg postgresql-client fonts-dejavu fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip==26.3 \
    && pip install --no-cache-dir -r requirements.lock
COPY bot.pyz ./
