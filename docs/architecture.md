# アーキテクチャ

## 責務分離

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

Resolver Core は UUID から current Description Location を返すだけです。Lab 内に `/relink/{uuid}` の Resolver 実装はありません。Resolver は AR-XML、Gateway、Pico の IP、Capability API を知りません。

## Lab の公開面

| 公開 route | PHP 実装 | 役割 |
| --- | --- | --- |
| `/` | `public/index.html` | 人間が操作する UI |
| `/arxml/pico2w.arxml` | 静的ファイル | Entity / Capability / Interface の宣言 |
| `/api/light/state` | `public/api/light-state.php` | boolean を enqueue し JSON result を返す |
| `/api/temperature` | `public/api/temperature.php` | temperature command を enqueue し JSON result を返す |
| `/device/commands` | `public/device/commands.php` | Pico が次の command を取得 |
| `/device/results/{id}` | `public/device/result.php` | Pico の result を相関保存 |

`.htaccess` は Web の route を PHP ファイルへ rewrite します。AR-XML と Web UI に PHP ファイル名を記述しません。

## SQLite command state

`src/LabStore.php` は DocumentRoot 外の `data/lab.sqlite` を共有します。

```text
queued → delivered → completed
                    ↘ failed
queued/delivered ───→ expired
```

各 row は `id`、`device_id`、`action`、`inputs_json`、`status`、`result_json`、`error_text`、`created_at`、`expires_at`、`completed_at` を保持します。`claimNext()` は transaction 内で expired queued row を先に廃棄し、未期限の command だけを delivered に変更します。Capability API は短い bounded wait 後に 504 を返し、timeout 時には queued/delivered row を expired にします。

同じ command ID の result は一度しか受け付けず、device ID が異なる result は拒否します。認証ではないため、公開運用時の認証・認可は別途必要です。

## Pico session

Pico は inbound port を開かず、Lab へ polling します。command はこのラボで定義した `light.setState` と `temperature.read` だけです。result POST の HTTP status が 200 以外なら例外として扱い、外側の reconnect/backoff へ戻ります。Wi-Fi 接続も固定時間で打ち切り、永久待機しません。

## Security boundary

L1 の `303`、Anchor UUID、HTTPS は Entity、所有者、AR-XML、Capability の真正性・認証・認可・安全性を証明しません。Resolver と Lab の HTTPS/CORS は独立しています。PHP endpoint には本番認証を追加していないため、公開前に前段の認証・認可、TLS、レート制限、監視を設計してください。
