# RELink Pico 2 W integrated setup

[日本語版](integrated-setup.ja.md)

This guide combines three repositories so a physical Pico 2 W Entity can be operated from a browser:

- [relink-resolver](https://github.com/ranmaru50/relink-resolver): resolves an Anchor UUID to an AR-XML location.
- [relink-web-runtime](https://github.com/ranmaru50/relink-web-runtime): loads AR-XML and interprets/invokes Capabilities in the browser.
- [relink-reference-lab](https://github.com/ranmaru50/relink-reference-lab): supplies the AR-XML, Web app, PHP Capability API, and Pico firmware.

This is an experimental reference setup. Before production use, separately verify TLS certificates, administration access control, secret storage, backups, and certificate validation on real Pico hardware.

## 1. Target topology

Replace example hostnames with real DNS names.

```text
Browser
    │ load Anchor URL
    ▼
Resolver: https://resolver.example/relink/{uuid}
    │ 303 See Other
    ▼
Lab: https://lab.example/arxml/pico2w.arxml
    │ resolve relative AR-XML endpoints
    ▼
Web app: Capability invoke
    │ POST /api/light/state or GET /api/temperature
    ▼
Lab PHP + SQLite command store
    ▲
    │ GET /device/commands?device_id=... / POST /device/results/{id}
    │ outbound-only HTTPS polling from the Pico
    │
Pico 2 W: LED control and RP2350 internal-temperature reading
```

Resolver does not interpret AR-XML or execute Capabilities. Its public L1 endpoint returns `303 See Other` to the registered ACTIVE Description Location. AR-XML interpretation and Capability execution belong to Web Runtime and this Lab.

## 2. Prerequisites

### Server

- A Linux host for a native installation or a host that can run Docker Compose.
- Apache 2.4; PHP 8.3+ with `pdo_sqlite`; Composer; SQLite CLI.
- An HTTPS DNS name and certificate.
- Separate Resolver and Lab hosts or VirtualHosts.
- Git, Node.js 20+, pnpm, Python 3.11+, and uv.

### Device

- Raspberry Pi Pico 2 W with compatible MicroPython.
- Wi-Fi or phone tethering.
- Network access from the Pico to the Lab HTTPS endpoint.

### Example URL allocation

| Role | Example URL |
| --- | --- |
| Resolver public URL | `https://resolver.example/relink/{uuid}` |
| Resolver administration | `https://resolver.example/admin.php` |
| Lab Web app | `https://lab.example/` |
| Lab AR-XML | `https://lab.example/arxml/pico2w.arxml` |
| Pico command base URL | `https://lab.example/device` |

## 3. Configure the Resolver

Run the Resolver as a separate service. Use its [implementation guide](https://github.com/ranmaru50/relink-resolver/blob/main/docs/implementation.md) for profile, environment, administration, and SQLite migration details.

### Native profile

Clone the Resolver outside the DocumentRoot and prepare its environment:

```bash
sudo mkdir -p /var/www
sudo git clone https://github.com/ranmaru50/relink-resolver.git /var/www/relink-resolver
cd /var/www/relink-resolver
sudo cp .env.example .env
sudo chmod 600 .env
sudoedit .env
```

At minimum, set production values such as:

```dotenv
RELINK_ENV=production
RELINK_ADMIN_USERNAME=resolver-admin
RELINK_ADMIN_PASSWORD=<strong-secret>
RELINK_DATA_DIR=/var/lib/relink-resolver
RELINK_SERVICE_PREFIX=/relink
```

When using a TLS-terminating proxy, configure only its source CIDRs in `RELINK_TRUSTED_PROXY_CIDRS` and sanitize `X-Forwarded-Proto` and one `X-Forwarded-For` value at the proxy. Do not enable `RELINK_ADMIN_ALLOW_HTTP=1` in production.

Install and migrate:

```bash
composer install --no-dev --classmap-authoritative
sudo install -d -o www-data -g www-data -m 0770 /var/lib/relink-resolver
sudo -u www-data php bin/migrate.php
```

Expose only `public/` from Apache. Keep `src/`, `migrations/`, `.env`, and SQLite outside the DocumentRoot. Enable `rewrite`, `headers`, `reqtimeout`, and, when Apache terminates TLS, `ssl`:

```bash
sudo a2enmod rewrite headers reqtimeout ssl
sudo a2ensite relink-resolver
sudo systemctl reload apache2
```

The current administration URL is `https://resolver.example/admin.php`. If `/admin/` is desired, add a Resolver-side rewrite.

### Container profile

```bash
git clone https://github.com/ranmaru50/relink-resolver.git
cd relink-resolver
cp .env.example .env
chmod 600 .env
editor .env
docker compose --env-file .env up --build -d
docker compose ps
docker compose logs resolver
```

The default `127.0.0.1:8080:80` mapping is a development loopback exposure. Put it behind a TLS proxy in production and restrict administration at the network layer. The entrypoint migrates before Apache starts; deleting the `resolver-data` volume deletes registration data.

### Register the Lab Entity

Register an ACTIVE record in the Resolver administration interface:

```text
Anchor UUID:
  550e8400-e29b-41d4-a716-446655440000

Canonical Entity Identity:
  https://lab.example/entities/pico2w-01

Description Location:
  https://lab.example/arxml/pico2w.arxml

Lifecycle:
  ACTIVE

Manifest publication:
  direct (this Lab does not use an optional Manifest)
```

Use a unique UUID in each environment. Register the final HTTPS AR-XML URL, never the Resolver URL or the Pico `/device` URL. Verify the HTTP response without asking the Resolver to fetch AR-XML:

```bash
curl -i https://resolver.example/relink/550e8400-e29b-41d4-a716-446655440000
```

Expect `303 See Other` and:

```text
Location: https://lab.example/arxml/pico2w.arxml
```

The public behavior for SUSPENDED is `404`; RETIRED is `410`.

## 4. Configure the Lab server and Web app

Clone the Lab and install dependencies:

```bash
git clone https://github.com/ranmaru50/relink-reference-lab.git
cd relink-reference-lab
composer install
pnpm install
uv sync
uv run python scripts/download_runtime.py
```

The download script obtains the v0.1.0 standalone ESM asset, verifies its pinned SHA-256 digest, and writes `public/vendor/relink-web-runtime.js`. Do not copy the Runtime source tree into the public DocumentRoot.

### SQLite and PHP

Keep SQLite outside the DocumentRoot and grant the Apache/PHP user access:

```bash
sudo install -d -o www-data -g www-data -m 0770 /var/lib/relink-reference-lab
sudo -u www-data env \
  LAB_DB_PATH=/var/lib/relink-reference-lab/lab.sqlite \
  php scripts/init_db.php
```

Configure:

```text
LAB_DB_PATH=/var/lib/relink-reference-lab/lab.sqlite
DEVICE_ID=pico2w-01
DEVICE_COMMAND_TIMEOUT=8
```

`LAB_DB_PATH` defaults to `data/lab.sqlite` inside the checkout. Use an explicit absolute path outside the DocumentRoot for a public deployment.

### Apache VirtualHost

```apache
<VirtualHost *:443>
    ServerName lab.example
    DocumentRoot /var/www/relink-reference-lab/public

    <Directory /var/www/relink-reference-lab/public>
        AllowOverride All
        Require all granted
    </Directory>

    Header always set Access-Control-Allow-Origin "*"
    Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
    Header always set X-Content-Type-Options "nosniff"
    Header always set Referrer-Policy "no-referrer"
</VirtualHost>
```

`Access-Control-Allow-Origin: *` is a simple reference-Lab setting. Authenticated or user-limited deployments should restrict it to the Web-app origin and align Resolver CORS with Lab/AR-XML CORS. When Resolver and Lab are different origins, both must permit the browser fetches.

### AR-XML and Web app

The fixture `public/arxml/pico2w.arxml` defines:

| Capability ID | Interface | Relative endpoint | Input/output |
| --- | --- | --- | --- |
| `light` | `POST`、JSON | `../api/light/state` | `{ "on": true/false }` → JSON scalar `boolean` |
| `temperature` | `GET` | `../api/temperature` | 入力なし → JSON scalar `number` |

Relative endpoints use the **final fetched AR-XML URL**, not the Resolver URL. With the example placement, `../api/...` resolves to the Lab API. Do not put the Pico `/device/commands` or `/device/results` routes in AR-XML; they are internal command-store traffic.

To add a Capability, define its `id`, semantic `type`, `inputs`, `result.outputs`, `result.representations`, and `interfaces`, then implement the PHP endpoint and Pico `execute_command()` together. Runtime does not execute arbitrary JavaScript from AR-XML.

The current UI is `public/index.html` and `public/app.js`. Set the Anchor URL default or enter it in the UI, select a language, load the Entity, and verify in the browser Network panel that the Anchor returns `303`, AR-XML returns `200`, no Capability is invoked on load, LED control produces `POST /api/light/state`, and temperature control produces `GET /api/temperature`.

Custom UIs should use the Runtime API shape:

```javascript
import { ARRuntime } from "@relink/web-runtime";

const runtimeDocument = await new ARRuntime().load(anchorUrl);
const light = runtimeDocument.getCapability("light");
const result = await light.invoke({ on: true }, { accept: "application/json" });
console.log(result.values);
```

This Lab loads the pinned standalone asset from `public/vendor/relink-web-runtime.js` instead of adding the package as a dependency.

## 5. Configure the Pico 2 W

Install compatible MicroPython and prepare a serial REPL or a transfer tool such as Thonny. If the firmware lacks an HTTP client, provide `urequests` and a configuration with TLS certificate validation. The Lab firmware supports:

```python
requests.get(url, timeout=seconds)
requests.post(url, data=json_text, headers=headers, timeout=seconds)
```

Copy `firmware/pico2w/config.example.py` to `config.py` and set:

```python
WIFI_SSID = "your-wifi-ssid"
WIFI_PASSWORD = "your-wifi-password"
GATEWAY_URL = "https://lab.example/device"
DEVICE_ID = "pico2w-01"
POLL_INTERVAL_SECONDS = 1
HTTP_TIMEOUT_SECONDS = 10
WIFI_CONNECT_TIMEOUT_SECONDS = 20
```

`DEVICE_ID` must exactly match the Lab server; `GATEWAY_URL` must be the Lab `/device` base URL, not the Resolver or `/api` URL. Never commit Wi-Fi credentials or HTTPS secrets.

Transfer `main.py` and `config.py` to the Pico (the latter is ignored by Git) and reboot it. The Pico then connects to Wi-Fi and starts polling.

### Device protocol

The Pico opens no inbound server:

1. Claim a command:

   ```text
   GET https://lab.example/device/commands?device_id=pico2w-01
   ```

   `204 No Content` means there is no command; `200 OK` contains `id`, `action`, and `inputs`.

2. Supported commands:

   ```json
   {"action":"light.setState","inputs":{"on":true}}
   {"action":"temperature.read","inputs":{}}
   ```

3. Post the result:

   ```text
   POST https://lab.example/device/results/{command_id}
   Content-Type: application/json
   ```

   Examples are `{"device_id":"pico2w-01","ok":true,"values":{"state":true}}`, `{"device_id":"pico2w-01","ok":true,"values":{"temperature":22.4}}`, and an error payload with `ok:false`.

If the result callback is not HTTP 200, the Pico enters reconnect/exponential backoff. Check the command ID, device ID, JSON shape, and command expiry.

### Physical check

Check the Pico serial log, open the Lab Web UI, enter the Resolver Anchor URL, and select **Load Entity**. Confirm that `light` and `temperature` appear without a command being issued. Test **LED ON**, **LED OFF**, and **Read temperature**, then correlate Apache logs, SQLite state, and Pico logs by command ID. The RP2350 internal temperature is not an accurate room-temperature sensor. Verify TLS validation, SNI, timeouts, memory, and Wi-Fi reconnection on the hardware.

## 6. Verification checklist

### Resolver

- [ ] The registered UUID returns `303`.
- [ ] `Location` points to the Lab HTTPS AR-XML URL.
- [ ] SUSPENDED returns `404`; RETIRED returns `410`.
- [ ] Administration requires HTTPS and authentication.
- [ ] SQLite and `.env` are outside the DocumentRoot.

### Lab / Web Runtime

- [ ] AR-XML returns `200`.
- [ ] Resolver and Lab CORS allow the browser cross-origin fetches.
- [ ] The Runtime asset is placed after SHA-256 verification.
- [ ] Loading does not execute a Capability.
- [ ] `light` and `temperature` appear.
- [ ] Relative endpoints resolve from the final AR-XML URL.

### Pico

- [ ] Wi-Fi values in `config.py` are correct.
- [ ] `DEVICE_ID` matches the server.
- [ ] `GATEWAY_URL` points to the Lab `/device` route.
- [ ] Polling receives `204` or `200`.
- [ ] Result callbacks return `200`.
- [ ] LED control and temperature reading complete on hardware.

## 7. Troubleshooting order

| Symptom | Check |
| --- | --- |
| Anchor load fails | Resolver `303`, Lab AR-XML `200`, TLS/CORS on both hosts, and browser Network panel |
| No Capabilities | AR-XML namespace/version, Runtime asset, and Runtime parse errors |
| Buttons stay disabled | `light`/`temperature` local IDs, AR-XML definitions, and Runtime load result |
| LED does not change | `POST /api/light/state`, SQLite command store, Pico polling, and matching `DEVICE_ID` |
| No temperature | `GET /api/temperature`, Pico ADC execution, result JSON, and HTTP status |
| Pico reconnects repeatedly | Wi-Fi/TLS/HTTP timeouts, endpoint reachability, and callback status |
| `403` or `404` | Device ID, command ID, result `device_id`, expiry, and Resolver lifecycle |

## 8. References

- [Resolver implementation guide](https://github.com/ranmaru50/relink-resolver/blob/main/docs/implementation.md)
- [Resolver container profile](https://github.com/ranmaru50/relink-resolver/blob/main/compose.yaml)
- [Resolver environment example](https://github.com/ranmaru50/relink-resolver/blob/main/.env.example)
- [Web Runtime README](https://github.com/ranmaru50/relink-web-runtime/blob/main/README.md)
- [Web Runtime package.json](https://github.com/ranmaru50/relink-web-runtime/blob/main/package.json)
- [Lab Apache/PHP setup](setup.md)
