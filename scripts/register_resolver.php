<?php
// scripts/register_resolver.php
/** 外部 Resolver の公式 application service を使ってサンプル Anchor を冪等登録する CLI。 */

declare(strict_types=1);

use Relink\Resolver\Adapters\SqliteResolverRepository;
use Relink\Resolver\Application\ApplicationException;
use Relink\Resolver\Application\ResolverService;
use Relink\Resolver\Domain\LifecycleState;

/** 必須環境変数を取得する。 */
function required_environment(string $name): string
{
    $value = getenv($name);
    if ($value === false || trim($value) === '') {
        throw new RuntimeException("{$name} is required");
    }
    return trim($value);
}

$resolverPath = rtrim(required_environment('RESOLVER_PATH'), DIRECTORY_SEPARATOR);
$bootstrapPath = $resolverPath . DIRECTORY_SEPARATOR . 'bootstrap.php';
if (!is_file($bootstrapPath)) {
    throw new RuntimeException("Resolver bootstrap not found: {$bootstrapPath}");
}

$config = require $bootstrapPath;
$uuid = required_environment('ANCHOR_UUID');
$location = required_environment('DESCRIPTION_LOCATION');
$entityId = required_environment('ENTITY_ID');
$service = new ResolverService(
    new SqliteResolverRepository($config['database_path']),
    $config['cache_max_age']
);

try {
    $record = $service->findRecord($uuid);
} catch (ApplicationException $error) {
    if ($error->errorCode !== 'NOT_FOUND') {
        throw $error;
    }
    $record = null;
}

if ($record === null) {
    $record = $service->register([
        'uuid' => $uuid,
        'state' => LifecycleState::ACTIVE->value,
        'location' => $location,
        'entity_id' => $entityId,
        'media_type' => 'application/xml',
        'publication_mode' => 'direct',
    ]);
    fwrite(STDOUT, "Resolver Anchor registered: {$record->anchor->value}\n");
    exit(0);
}

// 再実行時は既存レコードを暗黙更新せず、完全互換な場合だけ成功とする。
if (
    $record->state !== LifecycleState::ACTIVE
    || $record->location->value !== $location
    || $record->entityId !== $entityId
    || $record->manifestEnabled
) {
    throw new RuntimeException(
        'The Anchor already exists with incompatible state, identity, location, or Manifest mode.'
    );
}

fwrite(STDOUT, "Resolver Anchor already compatible: {$record->anchor->value}\n");
