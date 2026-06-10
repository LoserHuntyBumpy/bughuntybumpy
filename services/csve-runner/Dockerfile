# MVP Closed-Shell-Runner: slim Python, kein DinD/Nix/Firecracker (Phase 2).
# Exit-Code-/Output-Assertion deterministisch. Airgap ueber sandbox-Netz.
FROM python:3.12-slim

RUN pip install --no-cache-dir pyyaml==6.0.2 \
    && useradd -m -u 10001 runner

COPY runner.py /opt/runner.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

USER runner
ENTRYPOINT ["/opt/entrypoint.sh"]
