# Apache + PHP + SQLite setup

[日本語版](setup.ja.md)

## Prerequisites

The Lab server uses Apache 2.4, PHP 8.1+, and PDO SQLite. The existing `relink-resolver` runs as a separate service. Composer installs PHPUnit/PHPStan; pnpm installs Vitest/ESLint.

## Initialize the Lab

1. Download the pinned Runtime asset:

   ```text
   uv run python scripts/download_runtime.py
   ```

2. Create the database with PHP and `pdo_sqlite`:

   ```text
   php scripts/init_db.php
   ```

3. Set the Apache DocumentRoot to `public/`, keep `data/` outside it, and enable overrides:

   ```apache
   <Directory "<checkout>/public">
       AllowOverride FileInfo
       Require all granted
   </Directory>
   ```

4. Let PHP/FPM read and write `data/lab.sqlite`. If another path is used, use the same `LAB_DB_PATH` during initialization and runtime.

5. Enable `mod_rewrite` for `public/.htaccess`.

## Register the Resolver

In the existing Resolver administration interface, register an ACTIVE record:

```text
UUID: 550e8400-e29b-41d4-a716-446655440000
Description Location: https://<lab-host>/arxml/pico2w.arxml
```

The public Anchor URL is:

```text
https://<resolver-host>/relink/550e8400-e29b-41d4-a716-446655440000
```

This lab does not provide `/relink/{uuid}`. Verify that the Resolver's `303 Location` and the static AR-XML are both reachable over HTTPS.

## Public HTTPS

Terminate TLS in Apache or a normal HTTPS hosting/reverse-proxy service. CORS for `public/arxml/pico2w.arxml` and the PHP API is configured for browser execution, but Resolver CORS and Lab/AR-XML CORS must be checked independently.

No custom domain is required; a provider HTTPS endpoint is sufficient. Certificates, DNS, and proxy headers belong to the Web infrastructure, not to RELink Resolver or AR-XML semantics.

## Configure the Pico

Copy `firmware/pico2w/config.example.py` to `config.py` on the Pico:

```python
DEVICE_ID = "pico2w-01"
GATEWAY_URL = "https://<lab-host>/device"
```

The Pico uses `GET /commands?device_id=...` and `POST /results/{command_id}`. Its `DEVICE_ID` must match the Gateway configuration.

This repository has not physically validated every MicroPython firmware, `urequests`, and CA-bundle combination. Verify TLS certificate validation, SNI, timeouts, and memory usage on the device before deployment.

## Verification commands

```text
composer install
composer test
composer static-analysis
pnpm install
pnpm test
pnpm lint
uv run pytest
uv run ruff check .
php -l src/LabStore.php
php -l public/api/light-state.php
php -l public/api/temperature.php
php -l public/device/commands.php
php -l public/device/result.php
uv run python scripts/apache_acceptance.py --base-url https://<lab-host>
```

PHPUnit covers SQLite command-store transitions, PHPStan checks PHP sources and tests, Vitest covers Web UI load, explicit invoke, no automatic execution, and error display, and ESLint checks the JavaScript. The final acceptance script exercises the real Apache route, static AR-XML, rewrite, JSON validation, OPTIONS/CORS, empty polling, and malformed-result HTTP status.
