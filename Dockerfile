FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY COIL_dataset_glosas_salud_1_2M.csv .
COPY COIL_catalogo_servicios_cubiertos.csv .
COPY COIL_catalogo_perfiles_cobertura.csv .

EXPOSE 80

CMD ["python", "-m", "streamlit", "run", "app.py",\
     "--server.port=80", \
     "--server.address=0.0.0.0",\
     "--server.headless=true"]

     