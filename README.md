# RELink Pico 2 W Reference Lab

Raspberry Pi Pico 2 W を物理 Entity として、既存の RELink Resolver、AR-XML Core 0.1 Draft 4、RELink Web Runtime 0.1.0、Apache + PHP + SQLite、Pico MicroPython を接続する最小 L1 参照ラボです。

このリポジトリは `relink-web-runtime`、`relink-resolver`、`relink-testbed` の代替実装ではありません。Resolver は既存の Apache + PHP + SQLite 実装を別サービスとして再利用し、Lab は AR-XML、Web UI、Capability API、デバイス command store を提供します。

## What this lab validates

このラボで検証するもの:

- Resolver Core 0.1 の L1 パス
- 既存 Resolver による UUID → `303 See Other` → AR-XML
- Runtime 0.1.0 による Resolver-mediated loading
- この fixture に対する AR-XML Draft 4 の解析・検証
- 最終 AR-XML URL を基準にした相対 Interface URL 解決
- 明示的な HTTP Capability invocation
- 物理出力: Pico オンボード LED
- 物理入力: RP2350 内部温度の読み取り

このラボが主張しないもの:

- Resolver L2 の真正性、認証、認可
- 本番 Capability authorization / security
- RELink 全体または AR-XML 全体への完全準拠
- Runtime による自動実行
- 正確な室温測定

## アーキテクチャ

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

境界は明示的に保ちます。

```text
Entity      ≠ Location
Capability  ≠ Interface
Description ≠ Execution
Resolution  ≠ Authentication
```

Resolver は UUID と current AR-XML Description Location の対応だけを扱い、AR-XML を fetch/parse したり Capability を実行したりしません。Web Runtime の `load()` は発見・記述処理であり、Capability 実行はユーザーがボタンを押したときの `invoke()` に限ります。

## 必要なもの

- Apache 2.4（`mod_rewrite`、`.htaccess` の `AllowOverride FileInfo`）
- PHP 8.1 以上（PDO、`pdo_sqlite`、JSON）
- SQLite 3
- Composer（PHPUnit / PHPStan の導入用）
- Node.js 20 以上、pnpm（Vitest / ESLint の導入用）
- Python 3.11 以上、`uv`（Runtime 取得・Apache acceptance 用）
- Raspberry Pi Pico 2 W、対応 MicroPython
- Wi-Fi またはスマートフォンのテザリング

Python はサーバー実行環境ではありません。Lab の Web/Capability/device endpoint は PHP、共有状態は DocumentRoot 外の SQLite が担当します。

## セットアップ

Resolver、AR-XML/Webアプリ、Pico 2 Wをまとめて構築する場合は、[統合セットアップ手順](docs/integrated-setup.md)を参照してください。

### 1. Runtime 0.1.0 を取得

Runtime のソースツリーはコピーせず、公開 standalone ESM asset を SHA-256 検証付きで取得します。

```text
uv run python scripts/download_runtime.py
```

取得先は `public/vendor/relink-web-runtime.js` です。URL と SHA-256 は取得スクリプトに固定され、アセット自体は Git 管理対象外です。

### 2. SQLite を初期化

```text
php scripts/init_db.php
```

既定のデータベースは `data/lab.sqlite` です。`data/` は Apache DocumentRoot の外側に置きます。別の場所を使う場合は Apache/PHP の `LAB_DB_PATH` を同じ絶対パスに設定してください。

### 3. Apache を設定

Apache VirtualHost の `DocumentRoot` をこのリポジトリの `public/` に設定し、次を許可します。

```apache
<Directory "<checkout>/public">
    AllowOverride FileInfo
    Require all granted
</Directory>
```

`public/.htaccess` が、PHP の実ファイル名を AR-XML と Web UI に露出させず、次の公開 route へ rewrite します。

```text
/api/light/state
/api/temperature
/device/commands?device_id=pico2w-01
/device/results/{command_id}
```

`LAB_DB_PATH`、`DEVICE_ID`、`DEVICE_COMMAND_TIMEOUT` は Apache の VirtualHost または PHP-FPM pool で設定します。公開時は通常の HTTPS reverse proxy / hosting で TLS を終端してください。

### 4. 既存 Resolver を登録

`relink-resolver` を別サービスとして起動し、管理面で次を登録します。Lab は Resolver の登録 API を再実装しません。

```text
Anchor UUID: 550e8400-e29b-41d4-a716-446655440000
Description Location: https://<lab-host>/arxml/pico2w.arxml
状態: ACTIVE
```

QR / Anchor には次のような既存 Resolver の公開 URL を設定します。

```text
https://<resolver-host>/relink/550e8400-e29b-41d4-a716-446655440000
```

通常の L1 は Resolver → AR-XML の直接 `303` であり、Manifest を前提にしません。

### 5. Pico 2 W を設定

`firmware/pico2w/config.example.py` を `config.py` として Pico にコピーし、Wi-Fi と Lab の device endpoint を設定します。

```python
WIFI_SSID = "your-wifi"
WIFI_PASSWORD = "your-password"
DEVICE_ID = "pico2w-01"
GATEWAY_URL = "https://<lab-host>/device"
```

`boot.py`、`main.py`、`config.py` を Pico のルートへ配置して再起動します。Pico は `GET /device/commands` → 実行 → `POST /device/results/{id}` を繰り返し、接続失敗時は指数 backoff します。

このリポジトリでは Pico 実機上の TLS/CA 検証を完了していません。MicroPython の `urequests` と使用する firmware の CA 検証、SNI、メモリ制限を実機で確認してから公開運用してください。

## 操作方法

1. `https://<lab-host>/` を開く。
2. 既存 Resolver の Anchor URL を入力し、「Entity を読み込む」を押す。
3. `light` と `temperature` が表示されることを確認する。
4. 「LED を ON/OFF」または「温度を読み取る」を押す。
5. LED の状態または JSON の温度値を確認する。

ロード・発見だけでは物理操作は発生しません。温度値は RP2350 内部温度で、正確な室温センサー値ではありません。

## テスト

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

PHP の単体テストは PHPUnit、PHP の静的解析は PHPStan、Web JavaScript の DOM 単体テストは Vitest + jsdom、JavaScript の静的解析は ESLint が担当します。Python の pytest / Ruff は Apache acceptance の配線補助と Runtime 取得スクリプトに限定しています。

PHP/Composer や Node/pnpm がない環境では該当コマンドを実行できないため、CI または各ツールを導入した環境で実行してください。

Apache の実 HTTP route は、Apache を起動した状態で次を実行します。

```text
uv run python scripts/apache_acceptance.py --base-url https://<lab-host>
```

この acceptance は static AR-XML、PHP rewrite 後の入力 validation、OPTIONS/CORS、empty device polling、malformed result response を実 request で確認します。Pico が接続している場合の成功経路は、続く手動チェックリストで確認します。

## 手動物理受け入れチェックリスト

- [ ] Pico が文書化した Wi-Fi / テザリングへ bounded timeout 内に接続する。
- [ ] Pico が outbound HTTPS device session を確立する。
- [ ] Anchor URL が既存 Resolver L1 から AR-XML URL へ `303` される。
- [ ] Web Runtime 0.1.0 が Anchor path をロードする。
- [ ] Web App に 2 Capability が表示される。
- [ ] `light.setState(true)` で LED が点灯する。
- [ ] `light.setState(false)` で LED が消灯する。
- [ ] `temperature.read()` が数値を返す。
- [ ] デバイス停止時に API が 504 を返し、UI がエラーを表示する。
- [ ] ロードだけでは Capability が実行されない。
- [ ] Apache acceptance が実 HTTP route、JSON status、CORS を確認する。

## トラブルシューティングと制限

- Runtime asset がない場合は download script を実行する。
- 504 は Pico の offline、Wi-Fi 断、command expiry、または timeout の可能性がある。
- `commands` が 204 のときは待機中 command がない。expired command は Pico へ配送されない。
- result の 404/403/409/5xx は Pico 側で成功扱いにせず backoff へ戻る。
- Pico が物理 command 実行後に result callback を失うと、物理 side effect は発生したが Web API は 504 になる可能性がある。command は再配送せず、at-most-once 寄りで扱う。
- SQLite command store は共有状態だが、単一 Lab 用の最小実装であり、認証・暗号化・高可用性は提供しない。
- Gateway/Capability API は Apache + PHP、Resolver は既存 `relink-resolver` という別責務である。

## 調査結果

Draft 4 の相対 endpoint、内部温度、MicroPython TLS/CA、SQLite session の観察は [docs/findings.md](docs/findings.md) に分類して記録しています。
