FROM python:3.11-slim

WORKDIR /app

ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py athena_client.py ./

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:80/_stcore/health', timeout=3)"

CMD ["python", "-m", "streamlit", "run", "app.py",\
     "--server.port=80", \
     "--server.address=0.0.0.0",\
     "--server.headless=true"]

