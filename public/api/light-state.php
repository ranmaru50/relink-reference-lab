<?php
// public/api/light-state.php
/** light.setState Capability の HTTP binding。 */

declare(strict_types=1);

require_once dirname(__DIR__, 2) . '/src/bootstrap.php';

lab_handle_options();
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    lab_json_response(405, ['error' => 'method not allowed']);
}

try {
    $payload = lab_read_json();
    if (array_keys($payload) !== ['on'] || !is_bool($payload['on'])) {
        throw new InvalidArgumentException('on must be a boolean');
    }
    $config = lab_config();
    $commandId = lab_store()->enqueue(
        $config['device_id'],
        'light.setState',
        $payload,
        $config['timeout_seconds']
    );
    $values = lab_store()->waitForResult($commandId, $config['timeout_seconds']);
    $state = $values['state'] ?? null;
    if (!is_bool($state)) {
        throw new LabStoreCommandFailed('device result state が boolean ではありません');
    }
    // Web Runtime の単一 Output 契約に合わせ、成功値は JSON scalar で返す。
    lab_json_response(200, $state);
} catch (InvalidArgumentException | JsonException $error) {
    lab_json_response(400, ['error' => $error->getMessage()]);
} catch (LabStoreTimeout $error) {
    lab_json_response(504, ['error' => $error->getMessage()]);
} catch (LabStoreCommandFailed $error) {
    lab_json_response(502, ['error' => $error->getMessage()]);
} catch (Throwable $error) {
    error_log($error->getMessage());
    lab_json_response(500, ['error' => 'internal server error']);
}
