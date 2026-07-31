# Runbook

Run commands on the node from the repository checkout without printing secret
files or environment contents.

## Health and status

```bash
docker compose ps
curl --fail --silent http://127.0.0.1:8443/health
docker compose logs --since=15m agent xray hysteria
```

Healthy agent startup means the one-time Django bootstrap completed and the
Xray HandlerService responds. A failed bootstrap leaves the agent unhealthy
after its bounded retries. Investigate connectivity and configuration, then
restart the agent manually; there is no recovery worker or periodic reconcile.

```bash
docker compose restart agent
```

## Profile delivery

Profile PUT and DELETE calls arrive through the loopback-only management port
or its explicitly configured private/TLS ingress. Hysteria auth remains inside
the Compose control network. Do not expose port 8000, Xray gRPC port 10085, or
the `/auth` route on a public interface.

For a new node, keep the central `VPNInstance` inactive, run the repeatable
central backfill, smoke-test both transports, and activate the node manually.
The node itself has no persistent profile database.

## Rollback boundary

Do not improvise an automatic rollback. Keep the node inactive or disable the
VPN product centrally, collect container status and redacted logs, and agree on
the exact release revision to deploy. Payments and subscriptions remain in
Django and are not removed by an infrastructure rollback.
