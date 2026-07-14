# Production API — OCR runs in the browser; backend handles CRM, email, WhatsApp.
FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
ENV HOST=0.0.0.0
EXPOSE 8000

CMD ["python", "run.py"]
