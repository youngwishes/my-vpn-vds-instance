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
- The agent has no published host port. A pinned unprivileged reverse proxy is
  the only management ingress and forwards only `GET /health` plus `PUT` and
  `DELETE /api/v1/profiles/<id>` to the agent. In particular, it never forwards
  `/auth`.
- Management ingress defaults to loopback for local use. For the MVP,
  production binds it to all host interfaces (`0.0.0.0`) without a host
  firewall or TLS. Bearer authentication and the proxy route allowlist remain
  enabled; the accepted plaintext exposure risk is tracked as an MVP boundary.
- Credentials, REALITY private material, and Hysteria TLS material are mounted
  from files under `secrets/`; that directory is ignored by Git.

## Development

```bash
uv sync
uv run pytest
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.local.yml config --quiet
```

The local override binds management ingress and both VPN listeners to loopback
high ports. It still expects local placeholder secret files; do not use
production credentials for local validation.

Deployment preparation and release gates are documented in
[`docs/DEPLOY.md`](docs/DEPLOY.md). Operational checks are in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).

Production deployment is one inventory-driven Ansible command. The node pulls
the application from GitHub, creates persistent node-specific transport keys,
and configures automatic Let's Encrypt renewal for its `sslip.io` hostname.
