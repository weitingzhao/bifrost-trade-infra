# Minimal monitor API image for K3s stg smoke (Session S4).
# Full bifrost-trade-api build replaces this in a later session.
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir "fastapi>=0.100.0" "uvicorn[standard]>=0.22.0"

COPY app.py /app/app.py

ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8765"]
