# --- asset build stage: compile Tailwind CSS + vendor Preline/htmx ----------
FROM node:20-slim AS assets

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY tailwind.config.js ./
COPY web/ web/
RUN npm run build

# --- runtime stage ----------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

COPY web/requirements.txt web_requirements.txt
RUN pip install --no-cache-dir -r web_requirements.txt

COPY utils/ utils/
COPY web/ web/
COPY VERSION VERSION

# Overwrite the committed assets with the freshly compiled ones so the image
# is always in sync with the current templates/config.
COPY --from=assets /app/web/static/css/app.css web/static/css/app.css
COPY --from=assets /app/web/static/js/vendor/ web/static/js/vendor/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
