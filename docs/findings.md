# Findings

この文書は、実装で得た観察を仕様変更と混同しないための記録です。

## Finding 1: 相対 Interface endpoint

- Observation: AR-XML を `/arxml/pico2w.arxml` から配信し、`../api/...` を Interface に記述すると Runtime 0.1.0 は最終文書 URL を基準に Capability URL を解決できる。
- Draft 4 ambiguity?: いいえ。Draft 4 は最終 AR-XML document URL を相対 URL の base とすることを示している。
- Implementation-specific?: Gateway の `/arxml` と `/api` のパス配置はこのラボ固有。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。

## Finding 2: Pico 内部温度

- Observation: RP2350 内部温度 ADC の値は protocol integration の number output として返せるが、室温センサー値ではない。
- Draft 4 ambiguity?: いいえ。`number` と `Cel` は結果契約の記述であり、センサー精度を保証しない。
- Implementation-specific?: はい。ADC channel と変換式は Pico firmware 固有。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。

## Finding 3: MicroPython TLS/CA

- Observation: `urequests` の TLS/CA 検証は MicroPython の配布物・ビルド差を含むため、このラボの開発環境だけでは物理的な検証結果にできない。
- Draft 4 ambiguity?: いいえ。TLS は既存 Web 基盤と実行環境の責任。
- Implementation-specific?: はい。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。必要ならデプロイメント運用文書で扱う。

## Finding 4: Gateway セッションの再起動

- Observation: インメモリ command queue は小さく理解しやすいが、再起動すると pending command が失われる。
- Draft 4 ambiguity?: いいえ。Gateway/device-session transport は AR-XML の外側の実装詳細。
- Implementation-specific?: はい。
- Core change candidate?: いいえ。
- Profile candidate?: いいえ。
