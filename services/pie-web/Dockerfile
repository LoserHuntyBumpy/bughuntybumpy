FROM python:3.12-slim

LABEL org.opencontainers.image.title="bughuntybumpy-pie-web" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/Nope-im-not-pro/BugHuntyBumpy" \
      org.opencontainers.image.authors="Nope-im-not-pro <nope-im-not-pro@keemail.me>"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates ./templates
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
