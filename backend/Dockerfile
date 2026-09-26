FROM python:3.11-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole package rather than listing modules, so a new file can't be left out.
COPY app ./app

ENV PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
