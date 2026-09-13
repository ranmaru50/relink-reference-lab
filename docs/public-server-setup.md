<!-- docs/public-server-setup.md -->
[日本語](public-server-setup.ja.md)

# Public Server Setup Guide for example.com (Fictional Values)

This guide describes how to deploy RELink Reference Lab and the external `relink-resolver` service on an Ubuntu 24.04 public server using the Issue #4 Linux bootstrap script.

All domains and IP addresses in this document are fictional documentation values. Replace them with values for your own environment before executing any command. The example address `192.0.2.10` is from TEST-NET-1 and is not a routable production address.

## Resulting layout

| Role | URL or location |
| --- | --- |
| Resolver | `https://resolver.example.com` |
| Lab UI | `https://lab.example.com` |
| Anchor | `https://resolver.example.com/relink/550e8400-e29b-41d4-a716-446655440000` |
| ARXML | `https://lab.example.com/arxml/pico2w.arxml` |
| Repository | `/opt/relink/relink-reference-lab` |
| Resolver application | `/opt/relink/relink-resolver` |
| Resolver database | `/var/lib/relink-resolver/resolver.sqlite` |
| Lab database | `/var/lib/relink-reference-lab/lab.sqlite` |
| Let's Encrypt files | `/etc/letsencrypt/live/resolver.example.com/` |

## 1. Prerequisites

- Ubuntu 24.04 or later (Debian 13 or later is also suitable).
- A public IPv4 address, represented here by `192.0.2.10`.
- A sudo-capable SSH account.
- Permission to edit DNS records and the provider's packet filter.

Use a non-root SSH account for administration. The bootstrap script uses `sudo` for packages, Apache, system users, and service configuration.

## 2. DNS and packet filtering

Create A records before requesting a certificate:

```text
resolver.example.com. A 192.0.2.10
lab.example.com.      A 192.0.2.10
```

Allow inbound TCP 22, 80, and 443 in the hosting provider's packet filter. On the server, configure UFW:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Port 80 is required for the HTTP-01 challenge and should remain available for redirects and renewal validation.

## 3. Place the repository

```bash
sudo install -d -o "$USER" -g "$USER" -m 0755 /opt/relink
git clone https://github.com/ranmaru50/relink-reference-lab.git \
  /opt/relink/relink-reference-lab
cd /opt/relink/relink-reference-lab
```

If the Issue #4 changes are not yet present on `main`, check out the prepared branch:

```bash
git fetch origin codex/issue-4-linux-bootstrap
git switch --detach FETCH_HEAD
```

## 4. Bootstrap with a local certificate

Run the first setup with the default local-CA mode:

```bash
sudo ./scripts/setup-linux.sh \
  --resolver-host resolver.example.com \
  --lab-host lab.example.com
```

The script installs the required packages, pins and installs the resolver runtime, creates both SQLite databases, registers the Anchor, writes Apache virtual hosts, and runs an acceptance check. It is designed to be idempotent, so rerunning it after a failed or interrupted step is supported.

The local certificate is suitable for initial smoke tests only. Public browsers will not trust it.

## 5. Obtain a Let's Encrypt certificate

Install Certbot and verify that the HTTP endpoint is reachable from the Internet:

```bash
sudo apt-get update
sudo apt-get install -y certbot
curl -I http://resolver.example.com/
```

### HTTP-01 (recommended when port 80 is open)

The Apache configuration serves `/.well-known/acme-challenge/` from `/var/www/html`. Request one certificate containing both host names:

```bash
sudo certbot certonly \
  --webroot -w /var/www/html \
  --cert-name resolver.example.com \
  --non-interactive --agree-tos \
  --email <operations-email> \
  -d resolver.example.com \
  -d lab.example.com
```

Replace `<operations-email>` with an address monitored by the operations team. Certbot stores the resulting certificate under `/etc/letsencrypt/live/resolver.example.com/`.

### DNS-01 (alternative)

If port 80 cannot be exposed, create the TXT records requested by Certbot below these names and wait for DNS propagation:

```text
_acme-challenge.resolver.example.com.
_acme-challenge.lab.example.com.
```

Manual DNS-01 validation is not automatically renewable. Use a DNS provider API plugin or an equivalent renewal hook for unattended renewal. Remove temporary challenge TXT records after validation; do not remove the A records.

## 6. Switch Apache to the public certificate

Pass the certificate files explicitly to the setup script:

```bash
sudo ./scripts/setup-linux.sh \
  --resolver-host resolver.example.com \
  --lab-host lab.example.com \
  --tls-mode public \
  --certificate-file /etc/letsencrypt/live/resolver.example.com/fullchain.pem \
  --certificate-key-file /etc/letsencrypt/live/resolver.example.com/privkey.pem
```

The script validates that the certificate covers both host names, runs `apache2ctl configtest`, enables the TLS virtual hosts, and reloads Apache. It also installs a Certbot deploy hook so successful renewals automatically trigger the same configuration test and reload.

In `public` mode, the default execution allowlist separates the public UI/AR-XML surface from execution: `/api/` and `/device/` are reachable only from localhost. Opt in to external Pico or management-network execution only by specifying explicit CIDRs.

```bash
sudo ./scripts/setup-linux.sh \
  --resolver-host resolver.example.com \
  --lab-host lab.example.com \
  --tls-mode public \
  --execution-allowlist 198.51.100.0/24 \
  --certificate-file /etc/letsencrypt/live/resolver.example.com/fullchain.pem \
  --certificate-key-file /etc/letsencrypt/live/resolver.example.com/privkey.pem
```

`198.51.100.0/24` is a documentation example. Replace it with the fixed CIDR of the Pico, VPN, or management network. Full-network entries such as `0.0.0.0/0` or `::/0` are rejected.

## 7. Verify the deployment

```bash
curl -sS -D - -o /dev/null \
  https://resolver.example.com/relink/550e8400-e29b-41d4-a716-446655440000
curl -o /dev/null -sS -w '%{http_code}\n' https://lab.example.com/
curl -o /dev/null -sS -w '%{http_code}\n' https://lab.example.com/arxml/pico2w.arxml
sudo apache2ctl configtest
sudo certbot renew --dry-run
```

Expected results:

- The Anchor returns HTTP 303 with `Location: https://lab.example.com/arxml/pico2w.arxml`.
- The Lab UI and ARXML return HTTP 200.
- Apache reports `Syntax OK`.
- Certbot's dry run completes successfully.
- Without an execution allowlist, external clients receive HTTP 403 for `/api/` and `/device/` in the default public mode.

Also check the certificate name and expiry with `sudo certbot certificates`, and confirm that the systemd `certbot.timer` is enabled. Test both host names from an external network, not only from the server itself.

## 8. Pico W configuration

The remaining device-side work is intentionally explicit:

1. Configure Wi-Fi credentials on the Pico W.
2. Install the supported MicroPython firmware and device application.
3. Set `GATEWAY_URL=https://lab.example.com/device`.
4. Set a unique `DEVICE_ID`, for example `pico2w-01`.
5. Invoke the device workflow and confirm that the Lab receives the request.

Do not place resolver administrator credentials in the device image.

## 9. Operations and rollback

- Keep the resolver administrator endpoint bound to localhost unless remote administration is explicitly required.
- In `public` mode, `/api/` and `/device/` are localhost-only by default. Supplying an allowlist enables Capability/device execution only from those CIDRs; HTTPS is not a substitute for authentication or authorization.
- Protect `/etc/relink-reference-lab/resolver-admin-password` with root-only permissions.
- Back up `/var/lib/relink-resolver/resolver.sqlite`, `/var/lib/relink-reference-lab/lab.sqlite`, and the relevant `/etc/letsencrypt` files.
- Monitor Apache, PHP, and resolver logs, certificate expiry, disk usage, and the health of `certbot.timer`.
- After package or repository updates, rerun the setup script and acceptance check, then inspect `apache2ctl configtest`.
- If configuration fails, the script restores the previous Apache site, hardening/PHP security, `/etc/hosts`, and managed Certbot hook state. It refuses to overwrite an unmarked existing hook. For manual rollback, restore the previous certificate paths and reload Apache only after `apache2ctl configtest` succeeds.

Never copy the fictional domain or address from this guide into production unchanged.
