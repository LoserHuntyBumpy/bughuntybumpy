FROM python:3.12-slim

LABEL org.opencontainers.image.title="bughuntybumpy-pie-scanner" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/Nope-im-not-pro/BugHuntyBumpy" \
      org.opencontainers.image.authors="Nope-im-not-pro <nope-im-not-pro@keemail.me>"

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scan.py persist.py entrypoint.sh /opt/
RUN chmod +x /opt/entrypoint.sh

ENTRYPOINT ["/opt/entrypoint.sh"]
