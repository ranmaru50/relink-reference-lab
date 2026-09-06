# Findings

実装時の観察を、Draft 4 の意味拡張と混同しないよう分類します。

## Finding 1: 相対 Interface endpoint

- Observation: `/public/arxml/pico2w.arxml` から `../api/light/state` と `../api/temperature` を解決すると、最終 AR-XML URL と同じ Lab origin の Capability API になる。
- Draft 4 ambiguity?: いいえ。相対 URL は最終 AR-XML document URL を base にする。
- Implementation-specific?: Apache の DocumentRoot と route 配置はこの Lab 固有。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。

## Finding 2: 共有 command state

- Observation: Apache + PHP では worker を跨ぐため、command queue と result correlation を SQLite に置く必要がある。`queued → delivered → completed/failed/expired` を transaction で保存する。
- Draft 4 ambiguity?: いいえ。Gateway/device-session transport は AR-XML の外側の実装詳細。
- Implementation-specific?: はい。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。

## Finding 3: Command expiry

- Observation: Capability API の bounded wait 後は command を expired にし、Pico の claim transaction でも期限切れ queued row を配送しない。これにより 504 後に未配送の古い物理 command が実行されることを防ぐ。
- Draft 4 ambiguity?: いいえ。
- Implementation-specific?: はい。デバイスがすでに delivered command を実行中の場合の cancellation semantics は別途必要。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。必要なら device transport 運用仕様で扱う。

## Finding 4: MicroPython TLS/CA

- Observation: `urequests` と firmware ごとの CA 検証、SNI、timeout、メモリ制約はこの環境で物理検証していない。
- Draft 4 ambiguity?: いいえ。TLS は既存 Web 基盤とデバイス実行環境の責任。
- Implementation-specific?: はい。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。デプロイメント受け入れで確認する。

## Finding 5: Result callback 喪失

- Observation: Pico が物理 command を実行した後に result POST を失うと、Gateway は API caller へ 504 を返し得る一方、物理 side effect は既に発生している。`delivered` command は再配送しないため、Lab v0.1 は at-most-once 寄りの ambiguous outcome になる。
- Draft 4 ambiguity?: いいえ。Capability transport の delivery guarantee は Core の外側。
- Implementation-specific?: はい。再試行、冪等キー、device acknowledgement を追加する場合は Gateway/device transport の設計。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。

## Finding 6: Malformed result

- Observation: `ok` が boolean でない、または成功時の `values` が object でない result は HTTP 400 とし、SQLite row を terminal `failed` に確定する。waiter は timeout ではなく device failure として終了する。
- Draft 4 ambiguity?: いいえ。HTTP error mapping はこの Lab の Capability API 実装詳細。
- Implementation-specific?: はい。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。
