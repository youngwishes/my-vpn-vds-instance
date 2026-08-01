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
   `vpn_agent_bind_address` to `0.0.0.0`, so Docker publishes the management
   listener on the node's public interface.
3. Put `vpn_agent_token`, `vpn_reality_private_key`,
   `vpn_hysteria_tls_cert`, and `vpn_hysteria_tls_key` in an encrypted Ansible
   Vault vars file. Never pass them on the command line or store them in Git.
4. The MVP playbook publishes the management proxy on all host interfaces
   without TLS or a host firewall. Bearer authentication and the
   proxy route allowlist remain enabled. The accepted risk is that management
   credentials and profile traffic cross the network in plaintext. The agent
   port, Xray gRPC, and Hysteria auth have no host publication; the proxy
   forwards only the documented health and profile management routes.

Generate the REALITY key pair with the pinned Xray binary and retain only the
private value in Vault. The matching public connection parameters belong in the
central `VPNInstance`. Supply a certificate and private key matching the
Hysteria SNI.

After deployment, set the central `VPNInstance.management_url` to
`http://<public-bind>:<management-port>`.

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
read-only secret files, uses the management proxy config from that checkout,
pulls immutable runtime images, builds the agent, and applies Compose. It does
not activate a Django `VPNInstance`; backfill, smoke, and manual activation
remain central administrative steps.
