# Findings

[日本語版](findings.ja.md)

These observations were recorded against the earlier Draft 4 lab and remain implementation notes. The current lab uses Draft 5's shared Interface / InterfaceUse HTTP model; the old endpoint-shaped XML is historical and is not the active fixture.

## Finding 1: Draft 5 HTTP route resolution

- Observation: The active fixture uses an Interface Realization base `../api/` and InterfaceUse operation paths `light/state` and `temperature`. The Runtime resolves the base and route from the final AR-XML URL.
- Draft 5 behavior?: The HTTP Extension defines base/path resolution; Entity Resolution only selects the AR-XML location.
- Implementation-specific?: Yes. The Apache DocumentRoot and route layout belong to this lab.
- Core change candidate?: No.
- Profile candidate?: No.

## Finding 2: Shared command state

- Observation: Apache + PHP workers need SQLite for command queue and result correlation across workers. The state is stored as `queued → delivered → completed/failed/expired` in transactions.
- Draft 5 Core scope?: Gateway/device-session transport is outside AR-XML.
- Implementation-specific?: Yes.
- Core change candidate?: No.
- Profile candidate?: No.

## Finding 3: Command expiry

- Observation: The Capability API expires a command after its bounded wait, and the Pico claim transaction does not deliver expired queued rows. This prevents an old undelivered physical command from running after a 504.
- Draft 5 Core scope?: Command expiry remains a device transport concern.
- Implementation-specific?: Yes. Cancellation semantics for an already delivered command are separate.
- Core change candidate?: No.
- Profile candidate?: No. If needed, handle it in device-transport operations.

## Finding 4: MicroPython TLS/CA

- Observation: The CA validation, SNI, timeout, and memory constraints of `urequests` and each firmware combination have not been physically validated in this environment.
- Draft 5 Core scope?: TLS belongs to the existing Web platform and device runtime.
- Implementation-specific?: Yes.
- Core change candidate?: No.
- Profile candidate?: No. Verify it during deployment acceptance.

## Finding 5: Lost result callback

- Observation: If the Pico loses the result POST after executing a physical command, the Gateway may return 504 even though the physical side effect occurred. Delivered commands are not redelivered, so Lab v0.1 has an ambiguous outcome close to at-most-once delivery.
- Draft 5 Core scope?: Capability delivery guarantees are outside Core.
- Implementation-specific?: Yes. Retries, idempotency keys, and device acknowledgements belong in Gateway/device transport design.
- Core change candidate?: No.
- Profile candidate?: No.

## Finding 6: Malformed result

- Observation: A result whose `ok` is not boolean, or whose successful `values` is not an object, receives HTTP 400 and permanently becomes `failed` in SQLite. The waiter ends as a device failure rather than a timeout.
- Draft 5 Core scope?: HTTP error mapping is an implementation detail of this lab's Capability API.
- Implementation-specific?: Yes.
- Core change candidate?: No.
- Profile candidate?: No.
