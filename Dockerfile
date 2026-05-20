FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py athena_client.py ./

EXPOSE 80

CMD ["python", "-m", "streamlit", "run", "app.py",\
     "--server.port=80", \
     "--server.address=0.0.0.0",\
     "--server.headless=true"]

