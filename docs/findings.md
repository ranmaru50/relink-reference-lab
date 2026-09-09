# Findings

[日本語版](findings.ja.md)

These implementation observations are classified so they are not confused with semantic extensions to Draft 4.

## Finding 1: Relative Interface endpoint

- Observation: Resolving `../api/light/state` and `../api/temperature` from `/public/arxml/pico2w.arxml` produces Capability API URLs on the same Lab origin as the final AR-XML URL.
- Draft 4 ambiguity?: No. Relative URLs use the final AR-XML document URL as their base.
- Implementation-specific?: Yes. The Apache DocumentRoot and route layout belong to this lab.
- Core change candidate?: No.
- Profile candidate?: No.

## Finding 2: Shared command state

- Observation: Apache + PHP workers need SQLite for command queue and result correlation across workers. The state is stored as `queued → delivered → completed/failed/expired` in transactions.
- Draft 4 ambiguity?: No. Gateway/device-session transport is outside AR-XML.
- Implementation-specific?: Yes.
- Core change candidate?: No.
- Profile candidate?: No.

## Finding 3: Command expiry

- Observation: The Capability API expires a command after its bounded wait, and the Pico claim transaction does not deliver expired queued rows. This prevents an old undelivered physical command from running after a 504.
- Draft 4 ambiguity?: No.
- Implementation-specific?: Yes. Cancellation semantics for an already delivered command are separate.
- Core change candidate?: No.
- Profile candidate?: No. If needed, handle it in device-transport operations.

## Finding 4: MicroPython TLS/CA

- Observation: The CA validation, SNI, timeout, and memory constraints of `urequests` and each firmware combination have not been physically validated in this environment.
- Draft 4 ambiguity?: No. TLS belongs to the existing Web platform and device runtime.
- Implementation-specific?: Yes.
- Core change candidate?: No.
- Profile candidate?: No. Verify it during deployment acceptance.

## Finding 5: Lost result callback

- Observation: If the Pico loses the result POST after executing a physical command, the Gateway may return 504 even though the physical side effect occurred. Delivered commands are not redelivered, so Lab v0.1 has an ambiguous outcome close to at-most-once delivery.
- Draft 4 ambiguity?: No. Capability delivery guarantees are outside Core.
- Implementation-specific?: Yes. Retries, idempotency keys, and device acknowledgements belong in Gateway/device transport design.
- Core change candidate?: No.
- Profile candidate?: No.

## Finding 6: Malformed result

- Observation: A result whose `ok` is not boolean, or whose successful `values` is not an object, receives HTTP 400 and permanently becomes `failed` in SQLite. The waiter ends as a device failure rather than a timeout.
- Draft 4 ambiguity?: No. HTTP error mapping is an implementation detail of this lab's Capability API.
- Implementation-specific?: Yes.
- Core change candidate?: No.
- Profile candidate?: No.
