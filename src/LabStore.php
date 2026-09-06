<?php
// src/LabStore.php
/** SQLite による共有 device command store。 */

declare(strict_types=1);

final class LabStoreTimeout extends RuntimeException
{
}

final class LabStoreCommandFailed extends RuntimeException
{
}

final class LabStore
{
    private PDO $pdo;

    /**
     * SQLite 接続を作成し、共有 command テーブルを初期化する。
     *
     * @param string $databasePath DocumentRoot 外の SQLite ファイル。
     */
    public function __construct(string $databasePath)
    {
        $directory = dirname($databasePath);
        if (!is_dir($directory) && !mkdir($directory, 0770, true) && !is_dir($directory)) {
            throw new RuntimeException('SQLite ディレクトリを作成できません');
        }

        $this->pdo = new PDO('sqlite:' . $databasePath, null, null, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_TIMEOUT => 5,
        ]);
        $this->pdo->exec('PRAGMA busy_timeout = 5000');
        $this->pdo->exec('PRAGMA journal_mode = WAL');
        $this->pdo->exec(
            'CREATE TABLE IF NOT EXISTS commands (' .
            'id TEXT PRIMARY KEY, device_id TEXT NOT NULL, action TEXT NOT NULL, ' .
            'inputs_json TEXT NOT NULL, status TEXT NOT NULL CHECK (' .
            "status IN ('queued','delivered','completed','failed','expired')), " .
            'result_json TEXT, error_text TEXT, created_at REAL NOT NULL, ' .
            'expires_at REAL NOT NULL, completed_at REAL)'
        );
        $this->pdo->exec(
            'CREATE INDEX IF NOT EXISTS commands_device_status ON commands(device_id, status, expires_at)'
        );
    }

    /**
     * Capability API の command を queued 状態で追加する。
     *
     * @param string $deviceId 対象 Pico の固定 device ID。
     * @param string $action AR-XML から公開された lab action。
     * @param array<string, mixed> $inputs 入力値。
     * @param float $timeoutSeconds command の有効時間。
     */
    public function enqueue(
        string $deviceId,
        string $action,
        array $inputs,
        float $timeoutSeconds
    ): string {
        $commandId = bin2hex(random_bytes(16));
        $now = microtime(true);
        $expiresAt = $now + max(0.1, $timeoutSeconds);
        $statement = $this->pdo->prepare(
            'INSERT INTO commands ' .
            '(id, device_id, action, inputs_json, status, created_at, expires_at) ' .
            'VALUES (:id, :device_id, :action, :inputs_json, \'queued\', :created_at, :expires_at)'
        );
        $statement->execute([
            ':id' => $commandId,
            ':device_id' => $deviceId,
            ':action' => $action,
            ':inputs_json' => json_encode($inputs, JSON_THROW_ON_ERROR),
            ':created_at' => $now,
            ':expires_at' => $expiresAt,
        ]);
        return $commandId;
    }

    /**
     * queued command を一件だけ delivered に遷移させて返す。
     * expired な command は Pico へ渡さず、同じ transaction で廃棄する。
     *
     * @return array{id: string, device_id: string, action: string, inputs: array<string, mixed>, expires_at: float}|null
     */
    public function claimNext(string $deviceId): ?array
    {
        $now = microtime(true);
        // 複数の Apache worker が同時に polling しても同じ command を二重配送しない。
        $this->pdo->exec('BEGIN IMMEDIATE');
        try {
            $expire = $this->pdo->prepare(
                "UPDATE commands SET status = 'expired', completed_at = :now " .
                "WHERE device_id = :device_id AND status = 'queued' AND expires_at <= :expired_now"
            );
            $expire->execute([
                ':device_id' => $deviceId,
                ':now' => $now,
                ':expired_now' => $now,
            ]);

            $select = $this->pdo->prepare(
                "SELECT id, device_id, action, inputs_json, expires_at FROM commands " .
                "WHERE device_id = :device_id AND status = 'queued' AND expires_at > :now " .
                'ORDER BY created_at ASC LIMIT 1'
            );
            $select->execute([':device_id' => $deviceId, ':now' => $now]);
            $row = $select->fetch(PDO::FETCH_ASSOC);
            if ($row === false) {
                $this->pdo->commit();
                return null;
            }

            $claim = $this->pdo->prepare(
                "UPDATE commands SET status = 'delivered' WHERE id = :id AND status = 'queued'"
            );
            $claim->execute([':id' => $row['id']]);
            if ($claim->rowCount() !== 1) {
                $this->pdo->commit();
                return null;
            }
            $this->pdo->commit();
            $inputs = json_decode((string) $row['inputs_json'], true, 512, JSON_THROW_ON_ERROR);
            if (!is_array($inputs)) {
                throw new RuntimeException('command inputs が object ではありません');
            }
            return [
                'id' => (string) $row['id'],
                'device_id' => (string) $row['device_id'],
                'action' => (string) $row['action'],
                'inputs' => $inputs,
                'expires_at' => (float) $row['expires_at'],
            ];
        } catch (Throwable $error) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            throw $error;
        }
    }

    /**
     * Pico の結果を delivered command に一度だけ保存する。
     *
     * @param array<string, mixed> $payload device result payload。
     * @return string accepted / not_found / device_mismatch / expired / completed / failed
     */
    public function complete(string $commandId, string $deviceId, array $payload): string
    {
        $statement = $this->pdo->prepare(
            'SELECT device_id, status FROM commands WHERE id = :id'
        );
        $statement->execute([':id' => $commandId]);
        $row = $statement->fetch(PDO::FETCH_ASSOC);
        if ($row === false) {
            return 'not_found';
        }
        if ((string) $row['device_id'] !== $deviceId) {
            return 'device_mismatch';
        }
        if ((string) $row['status'] !== 'delivered') {
            return (string) $row['status'];
        }
        if (!isset($payload['ok']) || !is_bool($payload['ok'])) {
            $this->markFailed($commandId, 'malformed result: ok must be boolean');
            return 'malformed';
        }

        $status = $payload['ok'] ? 'completed' : 'failed';
        $values = $payload['values'] ?? null;
        $errorText = $payload['error'] ?? null;
        if ($payload['ok'] && !is_array($values)) {
            $this->markFailed($commandId, 'malformed result: values must be an object');
            return 'malformed';
        }
        $update = $this->pdo->prepare(
            'UPDATE commands SET status = :status, result_json = :result_json, ' .
            'error_text = :error_text, completed_at = :completed_at ' .
            "WHERE id = :id AND status = 'delivered'"
        );
        $update->execute([
            ':status' => $status,
            ':result_json' => $payload['ok']
                ? json_encode($values, JSON_THROW_ON_ERROR)
                : null,
            ':error_text' => is_string($errorText) ? $errorText : null,
            ':completed_at' => microtime(true),
            ':id' => $commandId,
        ]);
        return $update->rowCount() === 1 ? 'accepted' : 'completed';
    }

    /** malformed result を delivered のまま残さず terminal failed にする。 */
    private function markFailed(string $commandId, string $errorText): void
    {
        $update = $this->pdo->prepare(
            "UPDATE commands SET status = 'failed', error_text = :error_text, " .
            "completed_at = :completed_at WHERE id = :id AND status = 'delivered'"
        );
        $update->execute([
            ':error_text' => $errorText,
            ':completed_at' => microtime(true),
            ':id' => $commandId,
        ]);
    }

    /**
     * command の結果を bounded wait で監視する。
     *
     * @return array<string, mixed> 完了した values。
     */
    public function waitForResult(string $commandId, float $timeoutSeconds): array
    {
        $deadline = microtime(true) + max(0.1, $timeoutSeconds);
        while (microtime(true) < $deadline) {
            $statement = $this->pdo->prepare(
                'SELECT status, result_json, error_text, expires_at FROM commands WHERE id = :id'
            );
            $statement->execute([':id' => $commandId]);
            $row = $statement->fetch(PDO::FETCH_ASSOC);
            if ($row === false) {
                throw new LabStoreCommandFailed('command が見つかりません');
            }
            $status = (string) $row['status'];
            if ($status === 'completed') {
                $values = json_decode((string) $row['result_json'], true, 512, JSON_THROW_ON_ERROR);
                if (!is_array($values)) {
                    throw new LabStoreCommandFailed('device result が object ではありません');
                }
                return $values;
            }
            if ($status === 'failed') {
                throw new LabStoreCommandFailed((string) ($row['error_text'] ?? 'device command failed'));
            }
            if ($status === 'expired') {
                throw new LabStoreTimeout('device command expired');
            }
            usleep(100000);
        }

        $expire = $this->pdo->prepare(
            "UPDATE commands SET status = 'expired', completed_at = :now " .
            "WHERE id = :id AND status IN ('queued', 'delivered')"
        );
        $expire->execute([':now' => microtime(true), ':id' => $commandId]);
        throw new LabStoreTimeout('device command timed out');
    }
}
