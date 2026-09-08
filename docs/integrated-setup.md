# RELink Pico 2 W 統合セットアップ手順

この文書は、次の3リポジトリを組み合わせて、Pico 2 W の物理 Entity をブラウザーから操作するまでの手順をまとめたものです。

- [relink-resolver](https://github.com/ranmaru50/relink-resolver): Anchor UUID から AR-XML の場所へ解決するサーバー
- [relink-web-runtime](https://github.com/ranmaru50/relink-web-runtime): AR-XML を読み込み、Capability を解釈・実行するブラウザー Runtime
- [relink-reference-lab](https://github.com/ranmaru50/relink-reference-lab): AR-XML、Webアプリ、PHP Capability API、Pico用ファームウェア

この手順は実験用・参照用です。本番環境では、TLS証明書、管理面のアクセス制御、秘密情報の保管、バックアップ、Pico実機の証明書検証を別途確認してください。

## 1. 完成後の構成

ホスト名は例です。実際のDNS名に置き換えてください。

```text
ブラウザー
    │ Anchor URL を load
    ▼
Resolver: https://resolver.example/relink/{uuid}
    │ 303 See Other
    ▼
Lab: https://lab.example/arxml/pico2w.arxml
    │ AR-XML の相対 endpoint を解決
    ▼
Webアプリ: Capability invoke
    │ POST /api/light/state または GET /api/temperature
    ▼
Lab PHP + SQLite command store
    ▲
    │ GET /device/commands?device_id=... / POST /device/results/{id}
    │ Picoからの outbound-only HTTPS polling
    │
Pico 2 W: LED操作・RP2350内部温度読み取り
```

ResolverはAR-XMLを解釈せず、Capabilityも実行しません。Resolverの公開L1は、登録されたACTIVEレコードのDescription Locationへ`303 See Other`を返します。AR-XMLの解釈とCapabilityの実行は、Web RuntimeとLabの責務です。

## 2. 事前に用意するもの

### サーバー

- Linuxサーバー（Native profile）またはDocker Composeを実行できるホスト
- Apache 2.4
- PHP 8.3以上、`pdo_sqlite`、Composer、SQLite CLI
- HTTPSのDNS名と証明書
- `relink-resolver`用ホストと、Lab用ホストまたはVirtualHost
- Git、Node.js 20以上、pnpm、Python 3.11以上、uv

### デバイス

- Raspberry Pi Pico 2 W
- 対応するMicroPython
- Wi-Fiまたはスマートフォンのテザリング
- PicoからLabのHTTPS endpointへ接続できるネットワーク

### URLの割り当て例

| 役割 | URL例 |
| --- | --- |
| Resolver公開URL | `https://resolver.example/relink/{uuid}` |
| Resolver管理画面 | `https://resolver.example/admin.php` |
| Lab Webアプリ | `https://lab.example/` |
| Lab AR-XML | `https://lab.example/arxml/pico2w.arxml` |
| Pico command base URL | `https://lab.example/device` |

## 3. Resolverサーバーの設定

ここでは、ResolverをLabとは別サービスとして配置します。ResolverのNative/Container profile、環境変数、管理面、SQLite migrationの詳細は、参照先の[Reference Resolver実装ガイド](https://github.com/ranmaru50/relink-resolver/blob/main/docs/implementation.md)を基準にしてください。

### 3.1 Native profileでインストールする場合

1. ResolverをDocumentRoot外へ取得します。

   ```bash
   sudo mkdir -p /var/www
   sudo git clone https://github.com/ranmaru50/relink-resolver.git /var/www/relink-resolver
   cd /var/www/relink-resolver
   ```

2. `.env.example`をコピーし、本番用の管理者情報とデータ保存先を設定します。`.env`はコミットせず、管理者パスワードはSecret管理または適切なファイル権限で保護します。

   ```bash
   sudo cp .env.example .env
   sudo chmod 600 .env
   sudoedit .env
   ```

   最低限、次の値を本番用に変更します。

   ```dotenv
   RELINK_ENV=production
   RELINK_ADMIN_USERNAME=resolver-admin
   RELINK_ADMIN_PASSWORD=<十分に強い秘密情報>
   RELINK_DATA_DIR=/var/lib/relink-resolver
   RELINK_SERVICE_PREFIX=/relink
   ```

   TLS終端プロキシの背後に置く場合だけ、プロキシの送信元CIDRを`RELINK_TRUSTED_PROXY_CIDRS`へ設定します。プロキシは`X-Forwarded-Proto`と単一の`X-Forwarded-For`をクライアント入力から上書きしてください。本番で`RELINK_ADMIN_ALLOW_HTTP=1`を設定しないでください。

3. Composer依存関係をインストールし、データディレクトリを作成してmigrationを実行します。

   ```bash
   cd /var/www/relink-resolver
   composer install --no-dev --classmap-authoritative
   sudo install -d -o www-data -g www-data -m 0770 /var/lib/relink-resolver
   sudo -u www-data php bin/migrate.php
   ```

4. Apacheに`public/`だけを公開します。`src/`、`migrations/`、`.env`、SQLiteファイルはDocumentRoot外に置きます。参照先の`deploy/apache-vhost.conf.example`をベースに、`ServerName`とパスを実環境へ変更してください。

   ```apache
   <VirtualHost *:443>
       ServerName resolver.example
       DocumentRoot /var/www/relink-resolver/public

       <Directory /var/www/relink-resolver/public>
           AllowOverride All
           Require all granted
       </Directory>
   </VirtualHost>
   ```

   参照先の設定例を配置してから編集する場合は、次のようにします。

   ```bash
   sudo cp deploy/apache-vhost.conf.example /etc/apache2/sites-available/relink-resolver.conf
   sudoedit /etc/apache2/sites-available/relink-resolver.conf
   ```

   `mod_rewrite`、`mod_headers`、`mod_reqtimeout`、必要に応じて`mod_ssl`を有効化します。Apache自身でTLSを終端する場合は、参照先の`deploy/apache-native-ssl-vhost.conf.example`を使い、秘密鍵をDocumentRoot外へ配置します。

   ```bash
   sudo a2enmod rewrite headers reqtimeout ssl
   sudo a2ensite relink-resolver
   sudo systemctl reload apache2
   ```

5. Resolverの管理画面へログインします。現在の参照実装の直接URLは次です。

   ```text
   https://resolver.example/admin.php
   ```

   `/admin/`という別名を使う場合は、Resolver側でそのURLを`admin.php`へ転送するrewriteを別途設定してください。

### 3.2 Container profileで起動する場合

1. Resolverを取得し、環境ファイルを作成します。

   ```bash
   git clone https://github.com/ranmaru50/relink-resolver.git
   cd relink-resolver
   cp .env.example .env
   chmod 600 .env
   editor .env
   ```

2. `.env`の`RELINK_ENV`、管理者情報、必要な公開URL・プロキシ設定を本番用に変更します。

3. Composeを起動します。標準設定の`127.0.0.1:8080:80`は開発用loopback公開です。本番ではTLS終端プロキシからこのポートへ接続し、管理面もネットワーク側で制限します。

   ```bash
   docker compose --env-file .env up --build -d
   docker compose ps
   docker compose logs resolver
   ```

   ComposeのentrypointはApache起動前に`bin/migrate.php`を実行します。SQLiteは`resolver-data` volumeへ保存されるため、volumeを削除すると登録情報も失われます。

### 3.3 ResolverへEntityを登録する

Resolverの管理画面で、LabのAR-XMLを指すレコードを登録します。現在のLabでは次の値を例として使用します。

```text
Anchor UUID:
  550e8400-e29b-41d4-a716-446655440000

Canonical Entity Identity:
  https://lab.example/entities/pico2w-01

Description Location:
  https://lab.example/arxml/pico2w.arxml

Lifecycle:
  ACTIVE

Manifest publication:
  direct（現在のLabでは任意Manifestを使用しない）
```

UUIDは実環境ごとに一意な値へ変更してください。`Description Location`は、ブラウザーから直接取得できるHTTPSの最終AR-XML URLです。ResolverのURLやPicoの`/device` URLを登録してはいけません。

登録後、ResolverがAR-XMLを取得するのではなく、HTTP応答だけを確認します。

```bash
curl -i https://resolver.example/relink/550e8400-e29b-41d4-a716-446655440000
```

期待する結果は`303 See Other`と、次の`Location`ヘッダーです。

```text
Location: https://lab.example/arxml/pico2w.arxml
```

ACTIVE以外の状態は公開仕様上、SUSPENDEDが`404`、RETIREDが`410`になります。状態変更は管理画面から行い、公開URLの動作で確認します。

## 4. LabサーバーとWebアプリの設定

### 4.1 Labを取得して依存関係を準備する

```bash
git clone https://github.com/ranmaru50/relink-reference-lab.git
cd relink-reference-lab

composer install
pnpm install
uv sync
uv run python scripts/download_runtime.py
```

`download_runtime.py`は、参照先`relink-web-runtime`のv0.1.0 standalone ESM assetを取得し、固定SHA-256を検証して`public/vendor/relink-web-runtime.js`へ配置します。RuntimeのソースツリーをLabの公開DocumentRootへコピーする必要はありません。

### 4.2 SQLiteとPHP実行環境を設定する

SQLiteファイルはDocumentRoot外へ置き、Apache/PHPの実行ユーザーが読み書きできるようにします。

```bash
sudo install -d -o www-data -g www-data -m 0770 /var/lib/relink-reference-lab
sudo -u www-data env \
  LAB_DB_PATH=/var/lib/relink-reference-lab/lab.sqlite \
  php scripts/init_db.php
```

ApacheまたはPHP-FPMへ、Resolver登録で使った`DEVICE_ID`と同じ値を設定します。

```text
LAB_DB_PATH=/var/lib/relink-reference-lab/lab.sqlite
DEVICE_ID=pico2w-01
DEVICE_COMMAND_TIMEOUT=8
```

`LAB_DB_PATH`を省略した場合の既定値は、Lab checkout内の`data/lab.sqlite`です。開発用の既定値は利用できますが、公開環境ではDocumentRoot外の絶対パスを明示してください。

### 4.3 Apache VirtualHostを設定する

LabのDocumentRootを`public/`にします。Labの`.htaccess`は`Options`と`Require`も使用するため、次のように`AllowOverride All`を設定します。

```apache
<VirtualHost *:443>
    ServerName lab.example
    DocumentRoot /var/www/relink-reference-lab/public

    <Directory /var/www/relink-reference-lab/public>
        AllowOverride All
        Require all granted
    </Directory>

    # AR-XMLとResolver-mediated fetchを許可する。必要なら本番のUI originへ限定する。
    Header always set Access-Control-Allow-Origin "*"
    Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
    Header always set X-Content-Type-Options "nosniff"
    Header always set Referrer-Policy "no-referrer"
</VirtualHost>
```

`Access-Control-Allow-Origin: *`は参照Labの簡易設定です。認証付き・利用者限定の構成では、許可するWebアプリoriginへ絞り、ResolverのCORS設定とも整合させてください。Resolverの公開URLとLabのAR-XML URLが別originの場合、ResolverとLabの両方からブラウザーの取得を許可する必要があります。

### 4.4 AR-XMLを設定する

現在のサンプルは`public/arxml/pico2w.arxml`です。AR-XMLは次のCapabilityを定義します。

| Capability ID | Interface | 相対endpoint | 入力・出力 |
| --- | --- | --- | --- |
| `light` | `POST`、JSON | `../api/light/state` | `{ "on": true/false }` → JSON scalar `boolean` |
| `temperature` | `GET` | `../api/temperature` | 入力なし → JSON scalar `number` |

相対endpointは、Resolver URLではなく**最終的に取得されたAR-XMLのURL**を基準に解決されます。そのため、次の配置では`../api/...`がLabの`/api/...`になります。

```text
AR-XML: https://lab.example/arxml/pico2w.arxml
../api/light/state → https://lab.example/api/light/state
../api/temperature → https://lab.example/api/temperature
```

AR-XMLを別ディレクトリへ移す場合は、相対パスがLab APIを指すか確認してください。Picoの`/device/commands`や`/device/results`をAR-XMLに記載してはいけません。これらはPicoとLab command store間の内部通信です。

独自Capabilityを追加する場合は、`id`、semantic `type`、`inputs`、`result.outputs`、`result.representations`、`interfaces`を定義し、対応するPHP endpointとPico側の`execute_command()`を同時に実装します。RuntimeはAR-XML内の任意JavaScriptを実行する仕組みではありません。

### 4.5 Webアプリを設定する

現在のWebアプリは`public/index.html`と`public/app.js`です。

1. `public/index.html`のAnchor URL初期値を実環境のResolver公開URLへ変更するか、ブラウザー画面で入力します。

   ```html
   <input
     id="anchor-url"
     value="https://resolver.example/relink/550e8400-e29b-41d4-a716-446655440000"
   />
   ```

2. `public/app.js`の`ARRuntime.load()`へAnchor URLを渡します。Runtimeが303を追従してAR-XMLを取得し、最終URL基準でInterface endpointを解決します。

3. Capability実行は、ユーザーがボタンを押したときだけ行われます。ページロードやAR-XMLの発見だけでLEDを操作しないことを確認します。

4. カスタムUIを追加する場合は、Runtimeの基本形に合わせて`load()`、`getCapability(localId)`、`invoke(inputs, options)`を使用します。

   ```javascript
   import { ARRuntime } from "@relink/web-runtime";

   const runtimeDocument = await new ARRuntime().load(anchorUrl);
   const light = runtimeDocument.getCapability("light");
   const result = await light.invoke({ on: true }, { accept: "application/json" });
   console.log(result.values);
   ```

   上記は`relink-web-runtime`の公開API形です。現在のLabは、依存関係としてパッケージを組み込む代わりに、固定版standalone assetを`public/vendor/relink-web-runtime.js`として読み込みます。

5. AR-XMLとWebアプリを公開し、ブラウザーのNetwork panelで次を確認します。

   - Resolver AnchorへのGETが`303`になる
   - `Location`先のAR-XMLが`200`で返る
   - AR-XML取得後もCapability invokeが自動発生しない
   - LED操作で`POST /api/light/state`が発生する
   - 温度操作で`GET /api/temperature`が発生する

## 5. Pico 2 Wの設定

### 5.1 MicroPythonを準備する

Pico 2 Wへ対応するMicroPythonをインストールし、シリアルREPLまたはThonny等の転送手段を用意します。HTTP clientが標準で含まれないファームウェアでは、`urequests`とTLS証明書検証を利用できる構成を別途用意してください。

このリポジトリの`main.py`は、`urequests`があればそれを使い、なければ`requests`を使います。使用するライブラリが次の呼び出しに対応していることを確認します。

```python
requests.get(url, timeout=seconds)
requests.post(url, data=json_text, headers=headers, timeout=seconds)
```

### 5.2 `config.py`を作成する

`firmware/pico2w/config.example.py`をPico上の`config.py`としてコピーし、実環境の値を設定します。

```python
WIFI_SSID = "your-wifi-ssid"
WIFI_PASSWORD = "your-wifi-password"
GATEWAY_URL = "https://lab.example/device"
DEVICE_ID = "pico2w-01"
POLL_INTERVAL_SECONDS = 1
HTTP_TIMEOUT_SECONDS = 10
WIFI_CONNECT_TIMEOUT_SECONDS = 20
```

重要な一致条件は次のとおりです。

- `DEVICE_ID`はLabサーバーの`DEVICE_ID`と完全一致させる
- `GATEWAY_URL`はLabの`/device` base URLを指定する
- `GATEWAY_URL`へResolver URLや`/api` URLを指定しない
- Wi-FiパスワードとHTTPS関連の秘密情報をGitへアップロードしない

### 5.3 ファームウェアを転送する

Picoへ次の2ファイルを転送します。

```text
firmware/pico2w/main.py   → Picoのmain.py
firmware/pico2w/config.py → Picoのconfig.py
```

`config.py`は`.gitignore`で除外されています。転送後にPicoを再起動すると、`main.py`がWi-Fiへ接続し、Labへpollingを開始します。

### 5.4 PicoとLab間のプロトコル

Picoは受信待ちサーバーを開かず、Labへoutbound接続します。

1. command取得:

   ```text
   GET https://lab.example/device/commands?device_id=pico2w-01
   ```

   - `204 No Content`: commandなし。次のpollingへ進む
   - `200 OK`: `id`、`action`、`inputs`を含むcommandを実行する

2. 現在サポートするcommand:

   ```json
   {"action":"light.setState","inputs":{"on":true}}
   {"action":"temperature.read","inputs":{}}
   ```

3. result callback:

   ```text
   POST https://lab.example/device/results/{command_id}
   Content-Type: application/json
   ```

   成功・失敗の例:

   ```json
   {"device_id":"pico2w-01","ok":true,"values":{"state":true}}
   {"device_id":"pico2w-01","ok":true,"values":{"temperature":22.4}}
   {"device_id":"pico2w-01","ok":false,"error":"unsupported lab command"}
   ```

4. result callbackが`200`以外の場合、Picoはエラーとして扱い、外側の再接続・指数バックオフへ戻ります。Lab側のcommand ID、device ID、JSON形式が一致しているか確認してください。

### 5.5 実機確認

1. PicoのシリアルログでWi-Fi接続と例外の有無を確認します。
2. ブラウザーでLab Webアプリを開き、Resolver Anchor URLを入力して「Entityを読み込む」を押します。
3. `light`と`temperature`が表示され、ロード直後にcommandが発行されていないことを確認します。
4. 「LEDをON」「LEDをOFF」を押し、PicoのオンボードLEDを確認します。
5. 「温度を読み取る」を押し、数値が表示されることを確認します。
6. Apacheアクセスログ、LabのSQLite状態、Picoのシリアルログをcommand IDで突き合わせます。

RP2350内部温度は正確な室温センサー値ではありません。TLSの証明書検証、SNI、timeout、メモリ使用量、Wi-Fi再接続は実機で確認してください。

## 6. 動作確認チェックリスト

### Resolver

- [ ] `https://resolver.example/relink/{uuid}`が登録済みUUIDに対して`303`を返す
- [ ] `Location`がLabのHTTPS AR-XML URLを指す
- [ ] SUSPENDEDが`404`、RETIREDが`410`になる
- [ ] 管理画面がHTTPSと認証を要求する
- [ ] SQLiteと`.env`がDocumentRoot外にある

### Lab / Web Runtime

- [ ] AR-XMLが`200`で取得できる
- [ ] ResolverとLabのCORSがブラウザーのcross-origin fetchに対応している
- [ ] Runtime assetがSHA-256検証済みで配置されている
- [ ] ロードだけではCapabilityを実行しない
- [ ] `light`と`temperature`が表示される
- [ ] Capabilityの相対endpointが最終AR-XML URL基準で正しく解決される

### Pico

- [ ] `config.py`のWi-Fi情報が正しい
- [ ] `DEVICE_ID`がサーバーと一致する
- [ ] `GATEWAY_URL`がLabの`/device`を指す
- [ ] command pollingが`204`または`200`を受け取る
- [ ] result callbackが`200`を返す
- [ ] LED操作と温度読み取りが実機で完了する

## 7. 障害時の確認順

| 症状 | 確認箇所 |
| --- | --- |
| Anchorのロードに失敗する | Resolverの`303`、Lab AR-XMLの`200`、両ホストのTLS/CORS、ブラウザーNetwork panel |
| Capabilityが表示されない | AR-XMLのnamespace/version、`public/vendor/relink-web-runtime.js`、Runtimeのparse error |
| ボタンが有効にならない | `light`/`temperature`のlocal ID、AR-XMLのCapability定義、Runtime load結果 |
| LEDが変化しない | Labの`POST /api/light/state`、SQLite command store、PicoのGET polling、`DEVICE_ID`一致 |
| 温度が表示されない | `GET /api/temperature`、PicoのADC実行、result callbackのJSONとHTTP status |
| Picoが繰り返し再接続する | Wi-Fi timeout、HTTPS証明書検証、HTTP timeout、Lab endpointの到達性、result callback status |
| `403`/`404`が返る | device ID、command ID、JSONの`device_id`、commandの期限切れ、Resolver lifecycle |

## 8. 参照資料

- [Resolver README（日本語）](https://github.com/ranmaru50/relink-resolver/blob/main/README.ja.md)
- [Resolver Reference Resolver実装ガイド](https://github.com/ranmaru50/relink-resolver/blob/main/docs/implementation.md)
- [Resolver Container profile](https://github.com/ranmaru50/relink-resolver/blob/main/compose.yaml)
- [Resolver環境変数の例](https://github.com/ranmaru50/relink-resolver/blob/main/.env.example)
- [Web Runtime README（日本語）](https://github.com/ranmaru50/relink-web-runtime/blob/main/README.ja.md)
- [Web Runtime package.json](https://github.com/ranmaru50/relink-web-runtime/blob/main/package.json)
- [Labの既存セットアップ手順](setup.md)
