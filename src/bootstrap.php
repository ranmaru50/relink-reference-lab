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

/** JSON response と Browser Capability API 用 CORS を返す。 */
function lab_json_response(int $status, array $payload): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Access-Control-Allow-Origin: *');
    header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type');
    header('Referrer-Policy: no-referrer');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    exit;
}

/** JSON body を最大 4 KiB の object として読み込む。 */
function lab_read_json(): array
{
    $length = (int) ($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($length <= 0 || $length > 4096) {
        throw new InvalidArgumentException('JSON body は 1 byte 以上 4096 bytes 以下で必要です');
    }
    $body = file_get_contents('php://input');
    if ($body === false) {
        throw new InvalidArgumentException('JSON body を読み込めません');
    }
    $value = json_decode($body, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($value) || array_is_list($value)) {
        throw new InvalidArgumentException('JSON body は object である必要があります');
    }
    return $value;
}

/** OPTIONS preflight を処理する。 */
function lab_handle_options(): void
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
        http_response_code(204);
        header('Access-Control-Allow-Origin: *');
        header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
        header('Access-Control-Allow-Headers: Content-Type');
        header('Referrer-Policy: no-referrer');
        exit;
    }
}
