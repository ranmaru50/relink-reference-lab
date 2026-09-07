<?php
// public/api/temperature.php
/** temperature.read Capability の HTTP binding。 */

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/src/bootstrap.php';

lab_handle_options();
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    lab_json_response(405, ['error' => 'method not allowed']);
}

try {
    $config = lab_config();
    $commandId = lab_store()->enqueue(
        $config['device_id'],
        'temperature.read',
        [],
        $config['timeout_seconds']
    );
    $values = lab_store()->waitForResult($commandId, $config['timeout_seconds']);
    lab_json_response(200, $values);
} catch (LabStoreTimeout $error) {
    lab_json_response(504, ['error' => $error->getMessage()]);
} catch (LabStoreCommandFailed $error) {
    lab_json_response(502, ['error' => $error->getMessage()]);
} catch (Throwable $error) {
    error_log($error->getMessage());
    lab_json_response(500, ['error' => 'internal server error']);
}
