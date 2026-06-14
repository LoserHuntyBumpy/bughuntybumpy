FROM python:3.12-slim

LABEL org.opencontainers.image.title="bughuntybumpy-csve-broker" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/Nope-im-not-pro/BugHuntyBumpy" \
      org.opencontainers.image.authors="Nope-im-not-pro <nope-im-not-pro@keemail.me>"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY broker.py runner_driver.py docker_driver.py vm_driver.py .
CMD ["python", "broker.py"]
