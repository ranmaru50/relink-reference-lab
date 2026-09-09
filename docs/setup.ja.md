# Apache + PHP + SQLite セットアップ

[English](setup.md)

## 前提

Lab のサーバー側は Apache 2.4 + PHP 8.1+ + PDO SQLite です。Resolver は別サービスとして既存 `relink-resolver` を使います。PHPUnit / PHPStan は Composer、Vitest / ESLint は pnpm で導入します。

## 初期化

1. Runtime を取得する。

   ```text
   uv run python scripts/download_runtime.py
   ```

2. `pdo_sqlite` が有効な PHP で DB を作る。

   ```text
   php scripts/init_db.php
   ```

3. Apache の DocumentRoot を `public/` に設定する。`data/` は DocumentRoot 外に残す。

   ```apache
   <Directory "<checkout>/public">
       AllowOverride FileInfo
       Require all granted
   </Directory>
   ```

4. PHP/FPM から `data/lab.sqlite` を読み書きできるようにする。別パスの場合は `LAB_DB_PATH` を初期化時と実行時で一致させる。

5. `public/.htaccess` の `mod_rewrite` を有効にする。

## Resolver の登録

既存 Resolver の管理面で、次を ACTIVE record として登録します。

```text
UUID: 550e8400-e29b-41d4-a716-446655440000
Description Location: https://<lab-host>/arxml/pico2w.arxml
```

公開 Anchor は次の Resolver URL です。

```text
https://<resolver-host>/relink/550e8400-e29b-41d4-a716-446655440000
```

この Lab は `/relink/{uuid}` を提供しません。Resolver が返す `303 Location` と static AR-XML がそれぞれ HTTPS で取得できることを確認します。

## 公開 HTTPS

Lab の Apache 自体、または通常の HTTPS hosting / reverse proxy で TLS を終端します。`public/arxml/pico2w.arxml` と PHP API の CORS はブラウザー実行に必要な範囲で設定しています。Resolver の CORS と AR-XML の CORS は別々に確認してください。

カスタムドメインは不要です。プロバイダーが提供する HTTPS endpoint で構いません。HTTPS の証明書・DNS・proxy header は Web インフラの責務であり、RELink Resolver / AR-XML semantics には含まれません。

## Pico 設定

`firmware/pico2w/config.example.py` を `config.py` として Pico にコピーします。

```python
DEVICE_ID = "pico2w-01"
GATEWAY_URL = "https://<lab-host>/device"
```

Pico の通信は `GET /commands?device_id=...` と `POST /results/{command_id}` です。Gateway の設定 `DEVICE_ID` と一致させます。

このリポジトリでは MicroPython の firmware、`urequests`、CA bundle の組み合わせを実機で検証していません。TLS の証明書検証、SNI、タイムアウト、メモリ使用量を実機で確認してから公開してください。

## 確認コマンド

```text
composer install
composer test
composer static-analysis
pnpm install
pnpm test
pnpm lint
uv run pytest
uv run ruff check .
php -l src/LabStore.php
php -l public/api/light-state.php
php -l public/api/temperature.php
php -l public/device/commands.php
php -l public/device/result.php
uv run python scripts/apache_acceptance.py --base-url https://<lab-host>
```

PHPUnit は SQLite command store の状態遷移を単体テストし、PHPStan は `src/`・`public/`・PHPUnit tests を解析します。Vitest は Web UI のロード、explicit invoke、自動実行なし、エラー表示を jsdom でテストし、ESLint は `public/app.js` とテスト/config を解析します。

最後の `apache_acceptance.py` は Apache を実際に経由し、static AR-XML、`.htaccess` rewrite 後の PHP route、JSON validation、OPTIONS/CORS、empty device polling、malformed result の HTTP status を検証します。Pico が接続している場合は、Web UI の explicit invoke で LED と温度の成功経路も確認します。
