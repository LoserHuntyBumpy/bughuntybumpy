FROM python:3.12-slim

LABEL org.opencontainers.image.title="bughuntybumpy-csve-broker" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/Nope-im-not-pro/BugHuntyBumpy" \
      org.opencontainers.image.authors="Nope-im-not-pro <nope-im-not-pro@keemail.me>"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY broker.py runner_driver.py docker_driver.py vm_driver.py .
# Non-root (F-002): Prozess laeuft als broker-User mit der GID der
# Host-Docker-Socket-Gruppe (Build-Arg), Socket-Zugriff ohne root-uid.
# Existiert die GID im Image bereits (z. B. 0 bei Docker Desktop),
# wird sie wiederverwendet statt neu angelegt.
ARG DOCKER_GID=999
RUN getent group "${DOCKER_GID}" >/dev/null || groupadd -g "${DOCKER_GID}" docker
RUN useradd -r -g "${DOCKER_GID}" -d /app broker
USER broker
CMD ["python", "broker.py"]
