# Architecture

[日本語版](architecture.ja.md)

## Separation of responsibilities

```text
Discovery / Description plane
QR / Anchor
  ↓
existing relink-resolver (Apache + PHP + SQLite)
  ↓ 303 Location: https://lab-host/arxml/pico2w.arxml
Apache static AR-XML
  ↓
Browser + RELink Web Runtime 0.1.0
  ↓ explicit RuntimeCapability.invoke()

Execution plane
Human → Web App → PHP Capability API
                  ↓
              SQLite command store
                  ⇅
              Pico outbound polling
```

Resolver Core only returns the current Description Location for a UUID. This lab does not implement `/relink/{uuid}`. Resolver does not know the AR-XML, Gateway, Pico IP address, or Capability API.

## Public Lab surface

| Public route | PHP implementation | Purpose |
| --- | --- | --- |
| `/` | `public/index.html` | Human-operated Web UI |
| `/arxml/pico2w.arxml` | Static file | Entity, Capability, and Interface declarations |
| `/api/light/state` | `public/api/light-state.php` | Enqueue a boolean and return the JSON result |
| `/api/temperature` | `public/api/temperature.php` | Enqueue a temperature command and return the JSON result |
| `/device/commands` | `public/device/commands.php` | Let the Pico claim its next command |
| `/device/results/{id}` | `public/device/result.php` | Correlate and store the Pico result |

`.htaccess` rewrites Web routes to PHP files. PHP filenames are not exposed in the AR-XML or Web UI.

## SQLite command state

`src/LabStore.php` shares `data/lab.sqlite` outside the DocumentRoot.

```text
queued → delivered → completed
                    ↘ failed
queued/delivered ───→ expired
```

Each row stores `id`, `device_id`, `action`, `inputs_json`, `status`, `result_json`, `error_text`, `created_at`, `expires_at`, and `completed_at`. `claimNext()` discards expired queued rows inside a transaction and delivers only unexpired commands. The Capability API returns 504 after a short bounded wait and expires queued or delivered rows on timeout.

Only one result is accepted for a command ID, and a result from another device ID is rejected. This is not authentication; production deployments need separate authentication and authorization.

## Pico session

The Pico does not open an inbound port. It polls the Lab. The only commands defined by this lab are `light.setState` and `temperature.read`. Any result POST other than HTTP 200 is treated as an error and returns to reconnect/backoff. Wi-Fi connection attempts also have a fixed timeout.

## Security boundary

L1 `303`, Anchor UUIDs, and HTTPS do not prove Entity ownership, AR-XML or Capability authenticity, authentication, authorization, or safety. Resolver HTTPS/CORS and Lab HTTPS/CORS are independent. The PHP endpoints do not include production authentication; design upstream authentication/authorization, TLS, rate limiting, and monitoring before public deployment.
