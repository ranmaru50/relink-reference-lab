<?php
// src/bootstrap.php
/** Lab Capability API と device endpoint の共通設定・HTTP helper。 */

declare(strict_types=1);

require_once __DIR__ . '/LabStore.php';

/**
 * 環境変数から lab 設定を取得する。
 *
 * @return array{database_path: string, device_id: string, timeout_seconds: float}
 */
function lab_config(): array
{
    $databasePath = getenv('LAB_DB_PATH');
    return [
        'database_path' => $databasePath !== false && $databasePath !== ''
            ? $databasePath
            : dirname(__DIR__) . '/data/lab.sqlite',
        'device_id' => getenv('DEVICE_ID') ?: 'pico2w-01',
        'timeout_seconds' => max(0.1, (float) (getenv('DEVICE_COMMAND_TIMEOUT') ?: '8')),
    ];
}

/** 共有 SQLite store をリクエスト内で一度だけ作成する。 */
function lab_store(): LabStore
{
    static $store = null;
    if ($store === null) {
        $config = lab_config();
        $store = new LabStore($config['database_path']);
    }
    return $store;
}

/** JSON response を返し、ブラウザーや中間 cache に内容を保持させない。 */
function lab_json_response(int $status, mixed $payload): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    exit;
}

/**
 * Origin 文字列を比較用に正規化し、HTTP(S) origin 以外を拒否する。
 *
 * @param string $origin 検証する Origin。
 * @return string|null 正規化した Origin。不正な値は null。
 */
function lab_normalize_origin(string $origin): ?string
{
    if ($origin === 'null' || preg_match('/[\x00-\x20\x7f]/', $origin) === 1) {
        return null;
    }

    $parts = parse_url($origin);
    if (
        $parts === false
        || !isset($parts['scheme'], $parts['host'])
        || !in_array(strtolower($parts['scheme']), ['http', 'https'], true)
        || isset($parts['user'])
        || isset($parts['pass'])
        || isset($parts['query'])
        || isset($parts['fragment'])
        || (isset($parts['path']) && !in_array($parts['path'], ['', '/'], true))
    ) {
        return null;
    }

    $scheme = strtolower($parts['scheme']);
    $host = strtolower($parts['host']);
    $port = $parts['port'] ?? null;
    if ($port !== null && ($port < 1 || $port > 65535)) {
        return null;
    }
    if (($scheme === 'http' && $port === 80) || ($scheme === 'https' && $port === 443)) {
        $port = null;
    }

    return $scheme . '://' . $host . ($port === null ? '' : ':' . $port);
}

/**
 * 設定済みの信頼する Web UI origin を取得する。
 *
 * @return list<string>
 */
function lab_allowed_origins(): array
{
    $configured = getenv('LAB_ALLOWED_ORIGINS');
    if ($configured === false || trim($configured) === '') {
        return [];
    }

    $origins = [];
    foreach (explode(',', $configured) as $origin) {
        $normalized = lab_normalize_origin(trim($origin));
        if ($normalized === null) {
            error_log('LAB_ALLOWED_ORIGINS に不正な origin が設定されています');
            continue;
        }
        $origins[] = $normalized;
    }
    return array_values(array_unique($origins));
}

/**
 * 現在の request と同じ origin を取得する。
 *
 * @return string|null
 */
function lab_current_origin(): ?string
{
    $scheme = strtolower((string) ($_SERVER['REQUEST_SCHEME'] ?? ''));
    if (!in_array($scheme, ['http', 'https'], true)) {
        $scheme = !empty($_SERVER['HTTPS']) && strtolower((string) $_SERVER['HTTPS']) !== 'off'
            ? 'https'
            : 'http';
    }

    $host = (string) ($_SERVER['HTTP_HOST'] ?? '');
    return $host === '' ? null : lab_normalize_origin($scheme . '://' . $host);
}

/**
 * same-origin または明示的に許可した origin からの browser request だけを認める。
 *
 * @return bool
 */
function lab_browser_origin_is_allowed(): bool
{
    $origin = $_SERVER['HTTP_ORIGIN'] ?? null;
    $fetchSite = strtolower((string) ($_SERVER['HTTP_SEC_FETCH_SITE'] ?? ''));
    if ($origin === null) {
        return $fetchSite === '' || in_array($fetchSite, ['same-origin', 'none'], true);
    }

    $normalized = lab_normalize_origin((string) $origin);
    if ($normalized === null) {
        return false;
    }

    $allowedOrigins = lab_allowed_origins();
    if ($fetchSite === 'cross-site' && !in_array($normalized, $allowedOrigins, true)) {
        return false;
    }
    return $normalized === lab_current_origin()
        || in_array($normalized, $allowedOrigins, true);
}

/**
 * JSON body を Content-Type と実 byte 数を検証して最大 4 KiB の object として読み込む。
 *
 * @return array<string, mixed>
 */
function lab_read_json(): array
{
    $contentType = strtolower(trim(explode(';', (string) ($_SERVER['CONTENT_TYPE'] ?? ''), 2)[0]));
    if ($contentType !== 'application/json') {
        throw new InvalidArgumentException('Content-Type は application/json である必要があります');
    }

    $lengthHeader = (string) ($_SERVER['CONTENT_LENGTH'] ?? '');
    if ($lengthHeader === '' || !ctype_digit($lengthHeader)) {
        throw new InvalidArgumentException('JSON body の Content-Length が不正です');
    }
    $length = (int) $lengthHeader;
    if ($length <= 0 || $length > 4096) {
        throw new InvalidArgumentException('JSON body は 1 byte 以上 4096 bytes 以下で必要です');
    }
    $body = file_get_contents('php://input');
    if ($body === false || strlen($body) !== $length || strlen($body) > 4096) {
        throw new InvalidArgumentException('JSON body を読み込めません');
    }
    $value = json_decode($body, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($value) || array_is_list($value)) {
        throw new InvalidArgumentException('JSON body は object である必要があります');
    }
    return $value;
}

/**
 * browser request の Origin を制限し、許可された場合のみ CORS preflight を返す。
 *
 * @param bool $allowBrowserOrigins Capability API では browser origin を許可する。
 */
function lab_handle_options(bool $allowBrowserOrigins = true): void
{
    $origin = $_SERVER['HTTP_ORIGIN'] ?? null;
    $fetchSite = $_SERVER['HTTP_SEC_FETCH_SITE'] ?? null;
    if ($allowBrowserOrigins) {
        if (!lab_browser_origin_is_allowed()) {
            lab_json_response(403, ['error' => 'origin not allowed']);
        }
        if ($origin !== null) {
            $normalized = lab_normalize_origin((string) $origin);
            if ($normalized === null) {
                lab_json_response(403, ['error' => 'origin not allowed']);
            }
            header('Access-Control-Allow-Origin: ' . $normalized);
            header('Vary: Origin', false);
        }
    } elseif ($origin !== null || $fetchSite !== null) {
        // Device route は Pico の server-to-server 通信専用で、browser を受け付けない。
        lab_json_response(403, ['error' => 'browser requests are not allowed']);
    }

    if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
        http_response_code(204);
        if ($allowBrowserOrigins && $origin !== null) {
            header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
            header('Access-Control-Allow-Headers: Content-Type');
        }
        header('Referrer-Policy: no-referrer');
        exit;
    }
}
