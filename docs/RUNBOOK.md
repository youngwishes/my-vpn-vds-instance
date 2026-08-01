# Runbook

Run commands on the node from the repository checkout without printing secret
files or environment contents.

## Health and status

```bash
docker compose ps
curl --fail --silent http://<public-ip>:8443/health
docker compose logs --since=15m management-proxy agent xray hysteria
```

Healthy agent startup means the one-time Django bootstrap completed and the
Xray HandlerService responds. A failed bootstrap leaves the agent unhealthy
after its bounded retries. Investigate connectivity and configuration, then
restart the agent manually; there is no recovery worker or periodic reconcile.

```bash
docker compose restart agent
```

## Profile delivery

Profile PUT and DELETE calls arrive through the path-restricted proxy published
on all host interfaces. The MVP has no TLS or host firewall on this route; the
accepted plaintext exposure is temporary. The matching central
`VPNInstance.management_url` is
`http://<public-ip>:<management-port>`. Hysteria auth continues
to call `http://agent:8000/auth` inside the Compose control network. The agent
has no host port, and the management proxy rejects `/auth` and every route or
method outside its allowlist. Do not expose port 8000 or Xray gRPC port 10085.

For a new node, keep the central `VPNInstance` inactive, run the repeatable
central backfill, smoke-test both transports, and activate the node manually.
The node itself has no persistent profile database.

## Hysteria certificate renewal

Each node has a Let's Encrypt certificate for its own dash-separated IPv4
`sslip.io` hostname. Certbot's systemd timer renews it. A deploy hook copies a
successfully renewed certificate into the runtime secret files and force
recreates only the Hysteria container so Docker mounts the new files.

Check the timer, current expiry and renewal log without printing key material:

```bash
systemctl is-enabled certbot.timer
systemctl is-active certbot.timer
systemctl list-timers certbot.timer
openssl x509 -in secrets/hysteria-tls.crt -noout -subject -issuer -dates
journalctl -u certbot.service --since=-7d --no-pager
```

Test ACME renewal, then separately exercise the installed deploy hook. Ubuntu
22.04 ships Certbot 1.21, which does not support `--run-deploy-hooks`:

```bash
certbot renew --dry-run
RENEWED_LINEAGE=/etc/letsencrypt/live/<dash-separated-ip>.sslip.io \
  /etc/letsencrypt/renewal-hooks/deploy/vpn-node-hysteria
```

TCP/80 must remain reachable from the Internet for standalone HTTP-01 renewal.
Do not manually replace `hysteria-tls.key` or print its contents.

## Rollback boundary

Do not improvise an automatic rollback. Keep the node inactive or disable the
VPN product centrally, collect container status and redacted logs, and agree on
the exact release revision to deploy. Payments and subscriptions remain in
Django and are not removed by an infrastructure rollback.
