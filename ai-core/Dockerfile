FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
# CUDA'siz CPU torch'u once kur (pyproject'teki torch>=2.0 bununla karsilanir),
# boylece varsayilan index'ten GPU surumu (~GB) cekilmez.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir .

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
