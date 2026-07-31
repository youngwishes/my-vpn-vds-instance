# VPN node agent

Stateless FastAPI agent for one VPN node. It manages one Xray
VLESS+REALITY inbound through HandlerService and authorizes Hysteria 2 clients
from the in-memory profile store. Django remains the only persistent source of
VPN profiles.

## Runtime layout

- Xray publishes TCP/443 and exposes its gRPC API only on the internal Compose
  network.
- Hysteria publishes UDP/443 and calls `http://agent:8000/auth` only on that
  network.
- Agent management defaults to loopback for local use. Production binds it to
  an explicit private or overlay address; the deploy firewall admits only the
  configured central backend CIDR. It is not a public TLS endpoint.
- Credentials, REALITY private material, and Hysteria TLS material are mounted
  from files under `secrets/`; that directory is ignored by Git.

## Development

```bash
uv sync
uv run pytest
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.local.yml config --quiet
```

The local override binds both VPN listeners to loopback high ports. It still
expects local placeholder secret files; do not use production credentials for
local validation.

Deployment preparation and release gates are documented in
[`docs/DEPLOY.md`](docs/DEPLOY.md). Operational checks are in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).
