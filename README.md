# RELink Pico 2 W Reference Lab

[日本語版](README.ja.md)

This repository is a minimal L1 reference lab that connects a Raspberry Pi Pico 2 W as a physical entity with the existing RELink Resolver, AR-XML Core 0.1 Draft 4, RELink Web Runtime 0.1.0, Apache + PHP + SQLite, and Pico MicroPython.

This lab is not a replacement for `relink-web-runtime`, `relink-resolver`, or `relink-testbed`. It reuses the existing Apache + PHP + SQLite implementation as a separate Resolver service and provides the AR-XML fixture, Web UI, Capability API, and device command store.

## What this lab validates

- The Resolver Core 0.1 L1 path.
- UUID → `303 See Other` → AR-XML resolution by the existing Resolver.
- Resolver-mediated loading with Web Runtime 0.1.0.
- Parsing and validation of the AR-XML Draft 4 fixture used by this lab.
- Relative Interface URL resolution based on the final AR-XML URL.
- Explicit HTTP Capability invocation.
- A physical output: the Pico onboard LED.
- A physical input: the RP2350 internal temperature reading.

This lab does not claim Resolver L2 authenticity, production authorization or security, complete RELink or AR-XML conformance, automatic Runtime execution, or accurate room-temperature measurement.

## Architecture

```text
[Discovery / Description]
QR / Anchor
  ↓
existing relink-resolver (Apache + PHP + SQLite)
  ↓ 303
Lab AR-XML (Apache static file: public/arxml/pico2w.arxml)
  ↓
Browser + RELink Web Runtime 0.1.0

[Execution]
Human → Web App → RuntimeCapability.invoke()
  → Lab Capability API (PHP)
  → SQLite command store / correlation
  ⇅ outbound-only HTTPS polling
Pico 2 W (MicroPython)
```

The boundaries are intentional:

```text
Entity      ≠ Location
Capability  ≠ Interface
Description ≠ Execution
Resolution  ≠ Authentication
```

The Resolver maps a UUID to the current AR-XML Description Location. It does not fetch or parse AR-XML and does not execute Capabilities. Web Runtime `load()` is discovery and description; Capability execution happens only when the user presses a button and calls `invoke()`.

## Requirements

- Apache 2.4 with `mod_rewrite` and `.htaccess` `AllowOverride FileInfo`.
- PHP 8.1+ with PDO, `pdo_sqlite`, and JSON.
- SQLite 3.
- Composer for PHPUnit and PHPStan.
- Node.js 20+ and pnpm for Vitest and ESLint.
- Python 3.11+ and `uv` for Runtime download and Apache acceptance.
- Raspberry Pi Pico 2 W with compatible MicroPython.
- Wi-Fi or phone tethering.

Python is not the server runtime. PHP serves the Web and Capability/device endpoints; SQLite stores shared state outside the Apache DocumentRoot.

## Setup

For an end-to-end setup of the Resolver, AR-XML/Web app, and Pico 2 W, see [the integrated setup guide](docs/integrated-setup.md) ([日本語](docs/integrated-setup.ja.md)). The shorter Apache/PHP setup is available in [docs/setup.md](docs/setup.md) ([日本語](docs/setup.ja.md)).

### 1. Download Runtime 0.1.0

Do not copy the Runtime source tree. Download the published standalone ESM asset and verify its SHA-256 digest:

```text
uv run python scripts/download_runtime.py
```

The asset is written to `public/vendor/relink-web-runtime.js` and is excluded from Git. The URL and digest are pinned in the download script.

### 2. Initialize SQLite

```text
php scripts/init_db.php
```

The default database is `data/lab.sqlite`. Keep `data/` outside the Apache DocumentRoot. If another location is used, set the same absolute `LAB_DB_PATH` for initialization and runtime.

### 3. Configure Apache

Set the Apache VirtualHost `DocumentRoot` to this repository's `public/` directory and allow overrides:

```apache
<Directory "<checkout>/public">
    AllowOverride FileInfo
    Require all granted
</Directory>
```

`public/.htaccess` hides PHP filenames from the AR-XML and Web UI and rewrites these public routes:

```text
/api/light/state
/api/temperature
/device/commands?device_id=pico2w-01
/device/results/{command_id}
```

Configure `LAB_DB_PATH`, `DEVICE_ID`, and `DEVICE_COMMAND_TIMEOUT` in the Apache VirtualHost or PHP-FPM pool. Terminate TLS with the normal HTTPS reverse proxy or hosting service before production use.

### 4. Register the existing Resolver

Run `relink-resolver` as a separate service and register the following values in its administration interface:

```text
Anchor UUID: 550e8400-e29b-41d4-a716-446655440000
Description Location: https://<lab-host>/arxml/pico2w.arxml
Lifecycle: ACTIVE
```

Use the Resolver's public URL in the QR code or Anchor:

```text
https://<resolver-host>/relink/550e8400-e29b-41d4-a716-446655440000
```

Normal L1 behavior is a direct Resolver → AR-XML `303`; it does not require a Manifest.

### 5. Configure the Pico 2 W

Copy `firmware/pico2w/config.example.py` to `config.py` on the Pico and set the Wi-Fi and device endpoint values:

```python
WIFI_SSID = "your-wifi"
WIFI_PASSWORD = "your-password"
DEVICE_ID = "pico2w-01"
GATEWAY_URL = "https://<lab-host>/device"
```

Copy `boot.py`, `main.py`, and `config.py` to the Pico root and reboot it. The Pico repeatedly performs `GET /device/commands`, executes the command, and posts to `POST /device/results/{id}`. Connection failures use exponential backoff.

TLS/CA verification on real Pico hardware has not been completed in this repository. Verify the MicroPython `urequests` implementation, firmware CA validation, SNI behavior, and memory limits before public deployment.

## Using the Web UI

1. Open `https://<lab-host>/`.
2. Select English or 日本語, enter the existing Resolver Anchor URL, and select **Load Entity**.
3. Confirm that `light` and `temperature` appear.
4. Select **LED ON**, **LED OFF**, or **Read temperature**.
5. Confirm the LED state or JSON temperature value.

Loading and discovery never cause a physical operation. The temperature is the RP2350 internal temperature, not an accurate room-temperature sensor reading.

## Tests

```text
composer install
composer test
composer static-analysis
pnpm install
pnpm test
pnpm lint
uv run pytest
uv run ruff check .
```

PHPUnit tests the SQLite command-store transitions, PHPStan checks PHP sources and tests, Vitest tests the Web UI's explicit load/invoke behavior and language switching, and ESLint checks JavaScript. Python tests and Ruff cover the Apache acceptance helper and Runtime download script.

When Apache is running, execute the real HTTP acceptance checks with:

```text
uv run python scripts/apache_acceptance.py --base-url https://<lab-host>
```

The acceptance script checks static AR-XML, rewrite and input validation, OPTIONS/CORS, empty device polling, and malformed result responses. Physical success paths require the manual checklist below.

## Manual physical acceptance checklist

- [ ] The Pico connects to the documented Wi-Fi or tethering within the bounded timeout.
- [ ] The Pico establishes an outbound HTTPS device session.
- [ ] The Anchor URL resolves through Resolver L1 to the AR-XML URL with `303`.
- [ ] Web Runtime 0.1.0 loads the Anchor path.
- [ ] The Web UI displays two Capabilities.
- [ ] `light.setState(true)` turns the LED on.
- [ ] `light.setState(false)` turns the LED off.
- [ ] `temperature.read()` returns a number.
- [ ] When the device is stopped, the API returns 504 and the UI displays an error.
- [ ] Loading alone never executes a Capability.
- [ ] Apache acceptance verifies real HTTP routes, JSON status, and CORS.

## Troubleshooting and limitations

- Run the Runtime download script when the asset is missing.
- A 504 may indicate an offline Pico, Wi-Fi failure, command expiry, or timeout.
- A `204` response from `commands` means there is no pending command; expired commands are not delivered.
- Treat 404/403/409/5xx result responses as failures on the Pico and return to backoff.
- If the Pico loses the result callback after a physical command, the side effect may have happened while the Web API returns 504. Commands are not redelivered and are intentionally close to at-most-once semantics.
- The SQLite command store is a minimal single-lab shared-state implementation. It does not provide authentication, encryption, or high availability.
- The Gateway/Capability API (Apache + PHP) and the existing `relink-resolver` are separate responsibilities.

## Findings

Observations about relative Draft 4 endpoints, internal temperature, MicroPython TLS/CA behavior, and SQLite sessions are classified in [docs/findings.md](docs/findings.md) ([日本語](docs/findings.ja.md)).
