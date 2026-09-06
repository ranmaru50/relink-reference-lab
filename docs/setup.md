# セットアップ補足

## Runtime アセット

`@relink/web-runtime` の npm ソースツリーや `src/` は取り込みません。次のスクリプトだけが v0.1.0 の standalone ESM asset を取得します。

```text
uv run python scripts/download_runtime.py
```

固定値:

```text
URL: https://github.com/ranmaru50/relink-web-runtime/releases/download/v0.1.0/relink-web-runtime.js
SHA-256: f18d739edabc23285abd5fb64fcc056f17aaf480ddd1e0b6bed1702f8aab9e46
```

アセットは `.gitignore` に含まれるため、クリーンチェックアウトの再現にはこのダウンロード手順が必要です。

## HTTPS とリバースプロキシ

開発サーバーは TLS 終端を持たない標準ライブラリ HTTP サーバーです。公開時は HTTPS 対応のホスティング、または HTTPS リバースプロキシから Gateway へ転送します。`PUBLIC_BASE_URL` はブラウザーから見える URL に合わせます。

```text
公開: https://lab.example/relink/<uuid>
303: Location: https://lab.example/arxml/pico2w.arxml
```

`X-Forwarded-Proto` は Gateway の公開 URL を推測するための認証機構ではありません。信頼できる自分のリバースプロキシからだけ付与し、通常は `PUBLIC_BASE_URL` を明示してください。

## Pico の TLS/CA

このリポジトリでは Pico の物理ボード上で TLS/CA 検証を完了していません。`main.py` は MicroPython の `urequests`（利用可能なら `requests`）に依存しますが、ファームウェアごとの証明書検証・SNI・メモリ制限は差があります。HTTPS endpoint へ接続できることを本番の証拠とみなさず、使用するビルドで CA 検証を確認してから運用してください。

## Resolver 登録

実際の `relink-resolver` では管理面から UUID と current Description Location を登録します。L1 の登録値は次の二つだけです。

```text
UUID: 550e8400-e29b-41d4-a716-446655440000
Location: https://<public-host>/arxml/pico2w.arxml
```

Manifest は登録や通常の `GET /relink/{uuid}` の前提にしません。
