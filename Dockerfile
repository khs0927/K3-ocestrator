FROM python:3.13-slim

ARG KIMI_INSTALL_URL=https://code.kimi.com/kimi-code/install.sh

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl git openssh-client tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /bin/bash orchestrator

USER orchestrator
ENV HOME=/home/orchestrator \
    PATH=/home/orchestrator/.local/bin:/home/orchestrator/.venv/bin:${PATH} \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KIMI_DISABLE_TELEMETRY=1

# The official installer verifies the downloaded Kimi Code release checksum.
RUN curl -fsSL "${KIMI_INSTALL_URL}" | bash \
    && kimi --version

WORKDIR /opt/gateway
COPY --chown=orchestrator:orchestrator . /opt/gateway
RUN python -m venv /home/orchestrator/.venv \
    && python -m pip install --no-cache-dir .

EXPOSE 8790
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8790"]
