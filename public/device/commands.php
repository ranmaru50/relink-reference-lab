<?php
// public/device/commands.php
/** Pico の outbound polling endpoint。 */

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/src/bootstrap.php';

lab_handle_options();
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    lab_json_response(405, ['error' => 'method not allowed']);
}

$config = lab_config();
if (($_GET['device_id'] ?? null) !== $config['device_id']) {
    lab_json_response(404, ['error' => 'device not found']);
}

try {
    $command = lab_store()->claimNext($config['device_id']);
    if ($command === null) {
        http_response_code(204);
        header('Access-Control-Allow-Origin: *');
        header('Referrer-Policy: no-referrer');
        exit;
    }
    lab_json_response(200, $command);
} catch (Throwable $error) {
    error_log($error->getMessage());
    lab_json_response(500, ['error' => 'internal server error']);
}
