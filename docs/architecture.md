# アーキテクチャ

## 二つの平面

```text
発見・記述平面
Anchor → Resolver L1 → 303 AR-XML URL → Runtime.load() → Capability discovery

実行平面
Human → Web App → RuntimeCapability.invoke() → Capability API → Gateway
                                                        ↓
                                             outbound-only HTTPS polling
                                                        ↓
                                                       Pico
```

発見・記述平面は Entity が何を提供するかを伝えます。実行平面は、アプリケーションまたは人間が選択したときだけ Capability を実行します。Runtime の `load()` は発見処理であり、自動実行ではありません。

## コンポーネント

### Resolver L1

Gateway の `/relink/{uuid}` は RFC 9562 UUID を lookup key として扱い、fixture の ACTIVE レコードだけを `303 See Other` で `/arxml/pico2w.arxml` へ転送します。Resolver は AR-XML を fetch/parse せず、Capability API も知りません。`l` の未対応値と、レベルなしの予約 `p` は fail closed します。

本番の Description Location は絶対 HTTPS URL である必要があります。開発用の HTTP はローカル確認用の明示的な例外です。

### AR-XML

`arxml/pico2w.arxml` は Draft 4 の最小 Entity です。`light` は boolean input を JSON POST し、`temperature` は JSON の number output を GET します。Interface endpoint は fixture の URL を基準にした相対 URLで、ホストアプリケーションや Anchor URL を基準にしません。

AR-XML には Pico firmware の挙動、Gateway の polling、Web UI の表示ロジックを記述していません。

### Gateway

Gateway は通常の Web Capability API と、デバイス向けの小さな outbound session を同じプロセスで提供します。

```text
POST /api/light/state       {"on": true|false}
GET  /api/temperature
GET  /device/commands?device_id=pico2w-01
POST /device/results/{id}
```

Capability API は command ID を発行して待機し、Pico の result と相関させます。デバイスが接続していない場合は bounded timeout 後に 504 を返します。デバイス API は上記の `light.setState` と `temperature.read` だけを受け付け、任意の URL や TCP payload を転送しません。

### Pico 2 W

Pico は inbound listener を公開しません。Wi-Fi 接続後、Gateway へ短い JSON command を polling し、オンボード LED または RP2350 内部温度 ADC を操作し、結果を POST します。接続エラー時は指数バックオフで再接続します。

## セキュリティ境界

L1 の成功は Entity、所有者、AR-XML、Capability の認証・認可・安全性を証明しません。Gateway の認証は v0.1 では実装していないため、公開する場合は前段の認証・認可と TLS を別途設計してください。Resolver の CORS と AR-XML の CORS は独立した Web 権限です。
