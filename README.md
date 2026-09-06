# RELink Pico 2 W Reference Lab

このリポジトリは、Raspberry Pi Pico 2 W を物理 Entity として使用する、RELink の最小 L1 エンドツーエンド参照ラボです。Resolver、AR-XML、RELink Web Runtime、Gateway、デバイスセッションを小さな構成で接続し、Web アプリケーションから Pico のオンボード LED と RP2350 内部温度読み取りを明示的に操作します。

このラボは `relink-web-runtime`、`relink-resolver`、`relink-testbed` の代替実装ではありません。各プロジェクトの仕様・公開リリースを独立したベースラインとして利用します。

## What this lab validates

このラボで検証するもの:

- Resolver Core 0.1 の L1 パス
- Runtime による Resolver 経由のロード
- 最終 AR-XML URL の処理
- この fixture に対する AR-XML Draft 4 の解析・検証
- この fixture で使う相対 Interface URL の解決
- 明示的な HTTP Capability 呼び出し
- 物理出力: Pico オンボード LED
- 物理入力: RP2350 内部温度の読み取り

このラボが主張しないもの:

- Resolver L2 の真正性
- 本番 Capability 認可
- 本番セキュリティ
- RELink 全体への完全準拠
- AR-XML 全体への完全準拠
- Runtime による自動実行

## アーキテクチャ

```text
Discovery / Description plane
QR / Anchor URL
        ↓
Gateway Resolver: GET /relink/{uuid} → 303
        ↓
AR-XML: /arxml/pico2w.arxml
        ↓
RELink Web Runtime 0.1.0: ARRuntime.load()
        ↓
Capability discovery

Execution plane
Human → Web App
          ↓ RuntimeCapability.invoke()
Gateway Capability API: /api/light/state, /api/temperature
          ↓ outbound-only device session
Pico 2 W: GET command → execute → POST result
```

境界は次のように保ちます。

```text
Entity      ≠ Location
Capability  ≠ Interface
Description ≠ Execution
Resolution  ≠ Authentication
```

Resolver は UUID と現在の AR-XML Description Location の対応だけを扱い、AR-XML を解釈したり Capability を選択・実行したりしません。Web Runtime はロード時に Capability を自動実行せず、呼び出しはボタン操作による明示的な `invoke()` のみです。

## 必要なもの

- Python 3.11 以上（標準ライブラリのみ）
- `uv` と `pytest`（テスト実行時）
- Raspberry Pi Pico 2 W
- Pico 2 W 用 MicroPython
- Wi-Fi またはスマートフォンのテザリング
- Runtime アセット取得時のインターネット接続

本番相当の公開には、Gateway の前段に通常の HTTPS リバースプロキシまたは HTTPS 対応ホスティングを置いてください。カスタムドメインは不要で、プロバイダーが提供する HTTPS URL で構いません。

## セットアップ

### 1. Runtime 0.1.0 を取得

Runtime は手動コピーせず、公開リリースのアセットを SHA-256 検証付きで取得します。

```text
uv run python scripts/download_runtime.py
```

取得先は `web/vendor/relink-web-runtime.js` です。このファイルは Git 管理対象外で、スクリプトにリリース URL とダイジェストを固定しています。

### 2. Gateway を起動

ローカル確認では次のように起動します。

```text
uv run python gateway/server.py
```

ブラウザーで `http://127.0.0.1:8000/` を開きます。Anchor URL は次の既定値です。

```text
http://127.0.0.1:8000/relink/550e8400-e29b-41d4-a716-446655440000
```

ローカルの HTTP は開発専用です。L1 の公開運用では、Gateway を HTTPS URL で公開し、`PUBLIC_BASE_URL` にその URL を設定してください。

```text
PUBLIC_BASE_URL=https://example.provider.invalid/lab uv run python gateway/server.py
```

Windows PowerShell の例:

```powershell
$env:PUBLIC_BASE_URL = "https://example.provider.invalid/lab"
uv run python gateway/server.py
```

`PUBLIC_BASE_URL` が `/lab` を含む場合は、リバースプロキシがそのパスを保ったまま Gateway に転送する必要があります。HTTPS 終端の設定、証明書、公開 DNS はホスティング環境の責任であり、RELink プロトコルには含めません。

### 3. Pico 2 W を設定

`firmware/pico2w/config.example.py` を `config.py` として Pico にコピーし、Wi-Fi と Gateway のデバイス API URL を設定します。

```python
WIFI_SSID = "your-wifi"
WIFI_PASSWORD = "your-password"
DEVICE_ID = "pico2w-01"
GATEWAY_URL = "https://example.provider.invalid/device"
```

`boot.py`、`main.py`、`config.py` を Pico のルートへ配置して再起動します。デバイスは次の順序で動作します。

```text
GET  {GATEWAY_URL}/commands?device_id={DEVICE_ID}
実行
POST {GATEWAY_URL}/results/{command_id}
再接続時は 1 秒から 30 秒まで指数バックオフ
```

この実装の MicroPython 上の TLS/CA 検証は、対応するファームウェアと HTTP クライアントを含む物理環境で検証済みではありません。`urequests` の TLS 実装が使用されるため、公開運用では CA 検証を実施できる Pico 用ビルド・クライアントで確認し、確認できない場合は本番用途に使用しないでください。リポジトリのローカル HTTP 動作はこの検証を代替しません。

### 4. Resolver 登録と Anchor / QR

このラボの開発用 Gateway は、fixture の UUID をローカルで登録済みとして扱います。実際の Resolver 環境を使う場合は、管理 API で次の値を登録し、公開された Resolver URL を QR または Anchor に設定してください。

```text
UUID: 550e8400-e29b-41d4-a716-446655440000
Description Location: https://<公開Gateway>/arxml/pico2w.arxml
状態: ACTIVE
```

本番の Resolver は `GET /relink/{uuid}` に対して、登録された絶対 HTTPS URL を `303 See Other` の `Location` ヘッダーで返します。Manifest は通常の L1 シリアル経路に含めません。

## 操作方法

1. Web アプリケーションの Anchor URL を確認して「Entity を読み込む」を押す。
2. 表示された Capability が `light` と `temperature` の 2 件であることを確認する。
3. 「LED を ON」または「LED を OFF」を押す。ロードだけでは LED は変化しない。
4. 「温度を読み取る」を押し、数値結果を確認する。
5. 温度は RP2350 内部温度であり、正確な室温センサー値として扱わない。

Gateway と Pico が接続していない場合、Capability API はタイムアウト後に HTTP 504 を返し、Web UI はエラーを表示します。

## 手動物理受け入れチェックリスト

- [ ] Pico が文書化した Wi-Fi / テザリングへ接続する。
- [ ] Pico が outbound device session を確立する。
- [ ] Anchor URL が Resolver Core L1 で AR-XML URL に解決される。
- [ ] Web Runtime 0.1.0 が Anchor 経由でロードされる。
- [ ] Web App に期待する 2 Capability が表示される。
- [ ] ユーザー操作による `light.setState(true)` でオンボード LED が点灯する。
- [ ] ユーザー操作による `light.setState(false)` でオンボード LED が消灯する。
- [ ] ユーザー操作による `temperature.read()` が数値を返す。
- [ ] タイムアウト・エラーがハングせず表示される。
- [ ] Entity のロード・発見だけでは Capability が呼び出されない。

## テスト

```text
uv run pytest
uv run ruff check .
```

テストは、UUID の L1 解決、HTTP ヘッダー、禁止されたコマンド、コマンド ID 相関、タイムアウト、入力検証、AR-XML fixture の必須要素を対象にします。Pico の物理動作と外部 HTTPS 終端は手動手順で確認します。

## トラブルシューティング

- `web/vendor/relink-web-runtime.js` がない: `uv run python scripts/download_runtime.py` を実行する。
- Capability がタイムアウトする: Gateway の `/device/commands` を Pico がポーリングしているか、`DEVICE_ID` と Gateway の `DEVICE_ID` が一致しているか確認する。
- `303` の後でロードできない: 公開運用では Resolver と Description Location の両方が HTTPS であること、AR-XML 配信の CORS とリバースプロキシのパスを確認する。
- LED が動かない: Pico 2 W 用 MicroPython と `Pin("LED")` が利用できることを確認する。温度値はセンサー校正値ではない。
- `504` が返る: デバイス未接続、Wi-Fi 切断、または `DEVICE_COMMAND_TIMEOUT` を超過している可能性がある。

## 既知の制限

- Gateway のデバイス API はこのラボ用の小さなコマンド集合だけを受け付ける。任意の TCP プロキシではない。
- インメモリセッションのため、Gateway 再起動時に待機中コマンドは失われる。
- 認証、Capability Grant、デバイス証明、Resolver L2、署名、監査ログは実装しない。
- Gateway 自体は標準ライブラリの開発用 HTTP サーバーであり、本番サーバー・TLS 終端ではない。
- `urequests` の MicroPython TLS/CA 動作はこのリポジトリでは物理検証していない。

## ラボの調査結果

実装上の観察と Draft 4 の曖昧さは [docs/findings.md](docs/findings.md) に分類して記録しています。
