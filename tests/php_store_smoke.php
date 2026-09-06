<?php
// tests/php_store_smoke.php
/** SQLite command state の最小 smoke test。 */

declare(strict_types=1);

require_once dirname(__DIR__) . '/src/LabStore.php';

$databasePath = tempnam(sys_get_temp_dir(), 'relink-lab-');
if ($databasePath === false) {
    throw new RuntimeException('一時 DB を作成できません');
}
unlink($databasePath);

try {
    $store = new LabStore($databasePath);
    $commandId = $store->enqueue('pico2w-01', 'light.setState', ['on' => true], 2);
    $command = $store->claimNext('pico2w-01');
    if ($command === null || $command['id'] !== $commandId || $command['action'] !== 'light.setState') {
        throw new RuntimeException('command claim に失敗しました');
    }
    if ($store->complete($commandId, 'pico2w-01', [
        'ok' => true,
        'values' => ['state' => true],
    ]) !== 'accepted') {
        throw new RuntimeException('command complete に失敗しました');
    }
    if ($store->waitForResult($commandId, 1)['state'] !== true) {
        throw new RuntimeException('result correlation に失敗しました');
    }

    $expiredId = $store->enqueue('pico2w-01', 'temperature.read', [], 0.1);
    usleep(200000);
    if ($store->claimNext('pico2w-01') !== null) {
        throw new RuntimeException('expired command が配送されました');
    }
    echo "PHP SQLite smoke test passed\n";
} finally {
    foreach ([$databasePath, $databasePath . '-wal', $databasePath . '-shm'] as $path) {
        if (is_file($path)) {
            unlink($path);
        }
    }
}
