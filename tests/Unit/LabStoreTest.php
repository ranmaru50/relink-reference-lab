<?php
// tests/Unit/LabStoreTest.php
/** SQLite command store の状態遷移を PHPUnit で検証する。 */

declare(strict_types=1);

namespace RelinkReferenceLab\Tests\Unit;

use LabStore;
use LabStoreCommandFailed;
use PHPUnit\Framework\TestCase;

final class LabStoreTest extends TestCase
{
    private string $databasePath;

    private LabStore $store;

    /** 各テストに独立した SQLite ファイルを作成する。 */
    protected function setUp(): void
    {
        $databasePath = tempnam(sys_get_temp_dir(), 'relink-lab-test-');
        if ($databasePath === false) {
            self::fail('テスト用 SQLite ファイルを作成できません');
        }
        unlink($databasePath);
        $this->databasePath = $databasePath;
        $this->store = new LabStore($databasePath);
    }

    /** SQLite 本体と WAL sidecar を後片付けする。 */
    protected function tearDown(): void
    {
        foreach ([$this->databasePath, $this->databasePath . '-wal', $this->databasePath . '-shm'] as $path) {
            if (is_file($path)) {
                unlink($path);
            }
        }
    }

    /** command ID と device ID で成功 result を相関できることを確認する。 */
    public function testCompletesCommandAndReturnsValues(): void
    {
        $commandId = $this->store->enqueue('pico2w-01', 'light.setState', ['on' => true], 2);
        $command = $this->store->claimNext('pico2w-01');

        self::assertNotNull($command);
        self::assertSame($commandId, $command['id']);
        self::assertSame('light.setState', $command['action']);
        self::assertSame('{"on":true}', json_encode($command['inputs'], JSON_THROW_ON_ERROR));
        self::assertSame('accepted', $this->store->complete($commandId, 'pico2w-01', [
            'ok' => true,
            'values' => ['state' => true],
        ]));
        self::assertSame(['state' => true], $this->store->waitForResult($commandId, 1));
    }

    /** 引数なし command の入力を Pico が受け取れる空 object として配送することを確認する。 */
    public function testSerializesEmptyCommandInputsAsObject(): void
    {
        $commandId = $this->store->enqueue('pico2w-01', 'temperature.read', [], 2);
        $command = $this->store->claimNext('pico2w-01');

        self::assertNotNull($command);
        self::assertSame($commandId, $command['id']);
        self::assertSame('{}', json_encode($command['inputs'], JSON_THROW_ON_ERROR));
    }

    /** 有効期限を過ぎた queued command をデバイスへ配送しないことを確認する。 */
    public function testDoesNotClaimExpiredCommand(): void
    {
        $this->store->enqueue('pico2w-01', 'temperature.read', [], 0.1);
        usleep(200000);

        self::assertNull($this->store->claimNext('pico2w-01'));
    }

    /** malformed result が HTTP 層へ戻る前に terminal failed へ確定することを確認する。 */
    public function testMalformedResultBecomesTerminalFailure(): void
    {
        $commandId = $this->store->enqueue('pico2w-01', 'temperature.read', [], 2);
        self::assertNotNull($this->store->claimNext('pico2w-01'));

        self::assertSame('malformed', $this->store->complete($commandId, 'pico2w-01', ['ok' => 'yes']));
        $this->expectException(LabStoreCommandFailed::class);
        $this->store->waitForResult($commandId, 1);
    }

    /** 別 device の result は状態を変更せず拒否することを確認する。 */
    public function testRejectsResultFromDifferentDevice(): void
    {
        $commandId = $this->store->enqueue('pico2w-01', 'light.setState', ['on' => false], 2);
        self::assertNotNull($this->store->claimNext('pico2w-01'));

        self::assertSame('device_mismatch', $this->store->complete($commandId, 'other-device', [
            'ok' => true,
            'values' => ['state' => false],
        ]));
    }
}
