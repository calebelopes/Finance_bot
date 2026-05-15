FROM python:3.12-slim

WORKDIR /app

COPY web/requirements.txt web_requirements.txt
RUN pip install --no-cache-dir -r web_requirements.txt

COPY utils/ utils/
COPY web/ web/
COPY VERSION VERSION

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
