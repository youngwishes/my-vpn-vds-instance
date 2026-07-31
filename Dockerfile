FROM ghcr.io/xtls/xray-core@sha256:a1644183accdb0b5be967093fe34be756fd5de15fe2ee0206e842ae17350967f AS xray
FROM ghcr.io/astral-sh/uv@sha256:15f68a476b768083505fe1dbfcc998344d0135f0ca1b8465c4760b323904f05a AS uv
FROM docker.io/library/python@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925 AS agent

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/

USER 65532:65532
EXPOSE 8000

ENTRYPOINT ["/bin/sh", "-ec"]
CMD ["export VPN_AGENT_TOKEN=\"$(cat /run/secrets/vpn_agent_token)\"; exec python -c 'import uvicorn; from src.app import create_app; from src.config import Settings; uvicorn.run(create_app(settings=Settings.from_environment()), host=\"0.0.0.0\", port=8000)'"]
