<?php
// public/device/result.php
/** Pico の command result callback endpoint。 */

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/src/bootstrap.php';

lab_handle_options();
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    lab_json_response(405, ['error' => 'method not allowed']);
}

$commandId = (string) ($_GET['id'] ?? '');
try {
    if (!preg_match('/^[a-f0-9]{32}$/', $commandId)) {
        throw new InvalidArgumentException('invalid command id');
    }
    $payload = lab_read_json();
    $deviceId = $payload['device_id'] ?? null;
    if (!is_string($deviceId) || $deviceId === '') {
        throw new InvalidArgumentException('device_id is required');
    }
    $result = lab_store()->complete($commandId, $deviceId, $payload);
    if ($result === 'accepted') {
        lab_json_response(200, ['accepted' => true]);
    }
    if ($result === 'not_found') {
        lab_json_response(404, ['error' => 'command not found']);
    }
    if ($result === 'device_mismatch') {
        lab_json_response(403, ['error' => 'device mismatch']);
    }
    if ($result === 'malformed') {
        lab_json_response(400, ['error' => 'malformed device result']);
    }
    lab_json_response(409, ['error' => 'command is no longer deliverable', 'status' => $result]);
} catch (InvalidArgumentException | JsonException $error) {
    lab_json_response(400, ['error' => $error->getMessage()]);
} catch (Throwable $error) {
    error_log($error->getMessage());
    lab_json_response(500, ['error' => 'internal server error']);
}
