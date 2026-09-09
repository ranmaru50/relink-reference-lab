<?php
// scripts/init_db.php
/** DocumentRoot 外の共有 SQLite command store を初期化する CLI。 */

declare(strict_types=1);

require_once dirname(__DIR__) . '/src/bootstrap.php';

$config = lab_config();
new LabStore($config['database_path']);
echo "SQLite initialized: {$config['database_path']}\n";
