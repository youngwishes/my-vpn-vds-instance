# Deploy

The playbook deploys one exact Git revision and never performs merge, rollback,
or product activation. Run it only after the repository release gate grants
deployment permission for the named SHA.

## Inputs

1. Copy `deploy/inventory.example.ini` to an untracked inventory and replace the
   reserved example hostname.
2. Copy `deploy/group_vars/vpn.example.yml` to
   `deploy/group_vars/vpn.yml` and set repository URL, backend URL, REALITY
   target/SNI/short ID, and Hysteria obfuscation value. Set
   `vpn_agent_bind_address` to an address already assigned to a private or
   overlay interface and `vpn_backend_source_cidr` to the central backend's
   private or overlay source CIDR.
3. Put `vpn_agent_token`, `vpn_reality_private_key`,
   `vpn_hysteria_tls_cert`, and `vpn_hysteria_tls_key` in an encrypted Ansible
   Vault vars file. Never pass them on the command line or store them in Git.
4. Ensure the host firewall admits only TCP/443 and UDP/443 publicly. The
   playbook binds agent management to the configured private address and adds
   an allow-before-deny `DOCKER-USER` rule using Docker DNAT's original
   destination and port. The enabled systemd unit reapplies it after Docker on
   reboot. Xray gRPC and Hysteria auth have no host publication.

Generate the REALITY key pair with the pinned Xray binary and retain only the
private value in Vault. The matching public connection parameters belong in the
central `VPNInstance`. Supply a certificate and private key matching the
Hysteria SNI.

After deployment, set the central `VPNInstance.management_url` to
`http://<private-or-overlay-bind>:<management-port>`. TLS is not required for
this network-restricted route; never point the URL at a public interface.

## Checks and deployment

Before the release gate:

```bash
uv run pytest
uv lock --check
docker compose -f docker-compose.yml config --quiet
ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml --syntax-check
```

After explicit deploy authorization, substitute the private inventory and the
approved 40-character release SHA:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml \
  --ask-vault-pass -e deploy_revision=<approved-release-sha>
```

The playbook installs Docker Compose and Git, checks out that SHA, renders
read-only secret files, pulls immutable runtime images, builds the agent, and
applies Compose. It does not activate a Django `VPNInstance`; backfill, smoke,
and manual activation remain central administrative steps.
