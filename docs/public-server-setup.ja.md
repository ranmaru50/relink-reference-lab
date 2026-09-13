<!-- docs/public-server-setup.ja.md -->
[English](public-server-setup.md)
# example.com 公開サーバー設定ガイド（架空値）

このガイドは、Issue #4 の Linux 一括セットアップを使い、Ubuntu 24.04 の公開サーバーへ RELink Reference Lab と外部 `relink-resolver` を配備する手順です。実サーバーで確認した構成を基準にしつつ、ドメインと IP アドレスは文書用の架空値へ置き換えています。実際の環境では自分の値に置き換えてください。

## 完成後の構成

| 役割 | URL／配置 |
| --- | --- |
| Resolver | `https://resolver.example.com` |
| Lab | `https://lab.example.com` |
| Resolver Anchor | `https://resolver.example.com/relink/550e8400-e29b-41d4-a716-446655440000` |
| AR-XML | `https://lab.example.com/arxml/pico2w.arxml` |
| Lab checkout | `/opt/relink/relink-reference-lab` |
| Resolver checkout | `/opt/relink/relink-resolver` |
| Resolver SQLite | `/var/lib/relink-resolver/resolver.sqlite` |
| Lab SQLite | `/var/lib/relink-reference-lab/lab.sqlite` |
| Let’s Encrypt | `/etc/letsencrypt/live/resolver.example.com/` |

Resolver は `303 See Other` で Lab の AR-XML へ転送します。Resolver のソースは Lab にコピーせず、両方の SQLite は DocumentRoot の外へ置きます。

## 1. 事前条件

- Ubuntu 24.04 以降。Debian は互換性試験が完了するまで、この bootstrap の対象外です。
- サーバーの公開 IPv4（文書例: `192.0.2.10`、TEST-NET-1）
- SSH で sudo を実行できる管理ユーザー
- DNS と Sakura 側パケットフィルターを変更できる権限

DNS に次の A レコードを登録します。

```text
resolver.example.com A 192.0.2.10
lab.example.com      A 192.0.2.10
```

Sakura 側のパケットフィルターでは、次の inbound を許可します。

```text
TCP 22   SSH（管理元に限定することを推奨）
TCP 80   Let’s Encrypt HTTP-01 検証
TCP 443  HTTPS
```

サーバー内の UFW も同じポートを許可します。SSH 接続を維持するため、22 番を先に許可してから有効化します。

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

## 2. リポジトリを配置

```bash
sudo install -d -o "$USER" -g "$USER" -m 0755 /opt/relink
git clone https://github.com/ranmaru50/relink-reference-lab.git \
  /opt/relink/relink-reference-lab
cd /opt/relink/relink-reference-lab
```

Issue #4 がまだ `main` に取り込まれていない場合は、作業ブランチを取得してから実行します。

```bash
git fetch origin codex/issue-4-linux-bootstrap
git switch --detach FETCH_HEAD
```

## 3. Lab と Resolver を一括構築

まず、公開証明書をまだ持っていない状態では実験用 CA で構築します。これにより Apache の HTTP-01 用 DocumentRoot と、Resolver／Lab の動作を先に検証できます。

```bash
sudo ./scripts/setup-linux.sh \
  --resolver-host resolver.example.com \
  --lab-host lab.example.com
```

このコマンドは、Apache／PHP 8.3／Composer／SQLite、固定 commit の Resolver、Runtime v0.1.0、SQLite、初期 Anchor、Apache VirtualHost、受け入れ検証を構成します。再実行しても互換する Anchor、データベース、秘密値を保持します。

公開証明書を取得する前に、サーバー外部のクライアントから実行面を確認します。次の2つはどちらも `403` になります。`-k` はこの実験用 CA の確認に限って使用してください。

```bash
curl -k -o /dev/null -sS -w '%{http_code}\n' https://lab.example.com/api/temperature
curl -k -o /dev/null -sS -w '%{http_code}\n' 'https://lab.example.com/device/commands?device_id=pico2w-01'
```

bootstrap が配置する PHP 制限は Apache のグローバルな `conf.d` に適用され、このホストで mod_php を使うすべての VirtualHost に影響します。専用の実験ホストで使用するか、共有ホストでは他の PHP アプリケーションへの影響を確認してください。

## 4. Certbot の導入と証明書取得

```bash
sudo apt-get update
sudo apt-get install -y certbot
```

TCP 80 が外部から到達できることを確認します。

```bash
curl -I http://resolver.example.com/
```

HTTP-01 方式で、両サブドメインを含む証明書を取得します。`<運用メールアドレス>` は更新通知を受け取るアドレスに置き換えてください。

```bash
sudo certbot certonly \
  --webroot -w /var/www/html \
  --cert-name resolver.example.com \
  --non-interactive --agree-tos \
  --email <運用メールアドレス> \
  -d resolver.example.com \
  -d lab.example.com
```

HTTP-01 が使えない場合は DNS-01 を使用できます。その場合、Certbot が表示する次の名前の TXT レコードを追加します。

```text
_acme-challenge.resolver.example.com
_acme-challenge.lab.example.com
```

DNS-01 の手動証明書は自動更新できないため、公開運用では HTTP-01、または DNS API の認証 hook を使ってください。

## 5. Let’s Encrypt 証明書を Apache に適用

```bash
sudo ./scripts/setup-linux.sh \
  --resolver-host resolver.example.com \
  --lab-host lab.example.com \
  --tls-mode public \
  --certificate-file /etc/letsencrypt/live/resolver.example.com/fullchain.pem \
  --certificate-key-file /etc/letsencrypt/live/resolver.example.com/privkey.pem
```

スクリプトは証明書の SAN と有効期限を検証し、`apache2ctl configtest` が成功した場合だけ reload します。証明書更新後に Apache を reload する Certbot deploy hook も `/etc/letsencrypt/renewal-hooks/deploy/` に登録します。

`public` mode の既定値では、公開 UI／AR-XML と実行面を分離するため、`/api/` と `/device/` は localhost からだけ許可されます。外部 Pico や管理ネットワークから実行面を利用する場合だけ、許可する CIDR を明示した opt-in を行います。

```bash
sudo ./scripts/setup-linux.sh \
  --resolver-host resolver.example.com \
  --lab-host lab.example.com \
  --tls-mode public \
  --execution-allowlist 198.51.100.0/24 \
  --certificate-file /etc/letsencrypt/live/resolver.example.com/fullchain.pem \
  --certificate-key-file /etc/letsencrypt/live/resolver.example.com/privkey.pem
```

`198.51.100.0/24` は文書用の例です。実際の Pico／VPN／管理ネットワークの固定 CIDR に置き換えてください。`0.0.0.0/0` や `::/0` のような全ネットワーク許可は指定できません。

## 6. 検証

```bash
curl -sS -D - -o /dev/null \
  https://resolver.example.com/relink/550e8400-e29b-41d4-a716-446655440000
curl -o /dev/null -sS -w '%{http_code}\n' https://lab.example.com/
curl -o /dev/null -sS -w '%{http_code}\n' https://lab.example.com/arxml/pico2w.arxml
sudo apache2ctl configtest
sudo certbot renew --dry-run
```

期待値は Resolver が `303`（`Location: https://lab.example.com/arxml/pico2w.arxml`）、Lab と AR-XML が `200`、Apache が `Syntax OK`、Certbot の dry-run が成功です。allowlistを指定していない既定のpublic modeでは、外部クライアントから `/api/` と `/device/` が `403` になることも確認してください。

HTTP-01 方式へ切り替えた後は、証明書取得に使った DNS-01 の一時 TXT レコードを削除できます。A レコードは削除しません。

## 7. Pico 2 W の残作業

サーバー構築後も、Pico 側では次を設定します。

- Wi-Fi 接続
- `GATEWAY_URL=https://lab.example.com/device`
- `DEVICE_ID=pico2w-01`
- 対応する MicroPython firmware の転送

ブラウザーから Lab を開き、Capability は自動実行されず、ユーザーが明示的に実行します。

## 運用上の注意

- Resolver 管理画面は Apache 設定で localhost からだけ許可しています。
- `public` mode でも `/api/` と `/device/` は既定で localhost 限定です。allowlist を指定した場合だけ、その CIDR からの Capability／device 実行を許可します。HTTPS は認証・認可の代替ではありません。
- Resolver 管理パスワードは `/etc/relink-reference-lab/resolver-admin-password` に root 専用で保存されます。文書やログへ転載しません。
- Certbot timer と deploy hook の稼働を定期的に確認します。
- SQLite と `/etc/letsencrypt` は定期バックアップします。
- 公開運用では OS、Apache、PHP、Resolver の更新方針と監視を別途決めます。
- 設定変更に失敗した場合、スクリプトは Apache site、hardening／PHP security、`/etc/hosts`、管理対象Certbot hookの直前状態へ戻します。markerのない既存hookは上書きせず失敗します。原因を修正して同じコマンドを再実行してください。
