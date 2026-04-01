FROM python:3.12-slim

WORKDIR /app

COPY dashboard/requirements.txt dashboard_requirements.txt
COPY requirements.txt bot_requirements.txt
RUN pip install --no-cache-dir -r dashboard_requirements.txt \
    && pip install --no-cache-dir fpdf2

COPY dashboard/app.py app.py
COPY dashboard/.streamlit .streamlit
COPY utils/ utils/
COPY VERSION VERSION

EXPOSE 8501

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
