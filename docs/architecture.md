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
Browser + RELink Web Runtime 0.2.0 (AR-XML Draft 5)
  ↓ local exact-identity lookup
Contract and Profile definition fixtures
  ↓ explicit RuntimeCapability.invoke()

Execution plane
Human → Web App → PHP Capability API
                  ↓
              SQLite command store
                  ⇅
              Pico outbound polling
```

Resolver Core only returns the current Description Location for a UUID. This lab does not implement `/relink/{uuid}`. Resolver does not know the AR-XML, Gateway, Pico IP address, or Capability API.

Entity Resolution ends at the AR-XML location. The browser resolves semantic definitions and evaluates Profile conformance separately. A Profile Claim is displayed independently from its resolved definition and evaluated result.

## Public Lab surface

| Public route | PHP implementation | Purpose |
| --- | --- | --- |
| `/` | `public/index.html` | Human-operated Web UI |
| `/arxml/pico2w.arxml` | Static file | Entity, Capability, and Interface declarations |
| `/definitions/` | Static JSON fixtures | Exact-versioned Capability Contracts and Profile definitions |
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

The Pico does not open an inbound port. It polls the Lab. The semantic Capabilities are `indicator.set` and `temperature.read`; the latter describes the RP2350 internal MCU temperature, not ambient temperature. Any result POST other than HTTP 200 is treated as an error and returns to reconnect/backoff. Wi-Fi connection attempts also have a fixed timeout.

The simulator Entity in `public/arxml/simulator-controller.arxml` uses a different local Capability ID and HTTP path while claiming the same `controller-monitor/1` Profile. It documents the interoperability boundary and does not add a second device backend to the physical Lab.

## Security boundary

L1 `303`, Anchor UUIDs, and HTTPS do not prove Entity ownership, AR-XML or Capability authenticity, authentication, authorization, or safety. Resolver HTTPS/CORS and Lab HTTPS/CORS are independent. The PHP endpoints do not include production authentication; design upstream authentication/authorization, TLS, rate limiting, and monitoring before public deployment.
