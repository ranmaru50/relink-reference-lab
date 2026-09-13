<?php
// public/config.js.php
/** セットアップ済み Resolver Anchor URL を Web UI へ公開する設定 endpoint。 */

declare(strict_types=1);

$resolverBaseUrl = rtrim(getenv('RESOLVER_BASE_URL') ?: 'https://resolver.example', '/');
$anchorUuid = getenv('ANCHOR_UUID') ?: '550e8400-e29b-41d4-a716-446655440000';
$anchorUrl = $resolverBaseUrl . '/relink/' . rawurlencode($anchorUuid);

header('Content-Type: application/javascript; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
echo 'globalThis.RELINK_LAB_CONFIG = '
    . json_encode(['anchorUrl' => $anchorUrl], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR)
    . ";\n";
