# tests/test_setup_linux.py
"""Linux 一括セットアップの安全性と固定依存関係を検証する。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup-linux.sh"
REGISTER_SCRIPT = ROOT / "scripts" / "register_resolver.php"


def test_setup_help_does_not_require_root() -> None:
    """help はシステムを変更せず一般ユーザーでも参照できる。"""
    if os.name == "nt":
        pytest.skip("Windows の bash path 変換はこの Linux 専用テストの対象外です")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash が利用できない環境です")

    result = subprocess.run(
        [bash, str(SETUP_SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--resolver-host" in result.stdout
    assert "--tls-mode" in result.stdout


def test_resolver_checkout_is_external_and_pinned() -> None:
    """Resolver source を vendor せず、完全な commit SHA へ固定する。"""
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "https://github.com/ranmaru50/relink-resolver.git" in setup
    assert "b790ac9770975b39b488a104125dc6510e1f54bf" in setup
    assert 'git clone --no-checkout "${RESOLVER_REPOSITORY}"' in setup
    assert 'checkout --detach "${RESOLVER_REVISION}"' in setup


def test_setup_preserves_resolver_management_boundary() -> None:
    """初期登録は SQLite 直書きではなく Resolver application service を使う。"""
    registration = REGISTER_SCRIPT.read_text(encoding="utf-8")

    assert "ResolverService" in registration
    assert "SqliteResolverRepository" in registration
    assert "publication_mode' => 'direct'" in registration
    assert "INSERT INTO resolver_records" not in registration


def test_apache_is_validated_before_reload() -> None:
    """新しい site は configtest 成功後にだけ reload される。"""
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")
    write_sites = setup[setup.index("write_apache_sites()") :]

    assert write_sites.index("apache2ctl configtest") < write_sites.index(
        "systemctl reload apache2"
    )
    assert "restore_apache_state" in setup


def test_setup_rejects_root_as_a_managed_path() -> None:
    """管理対象 path に / を許可せず、システム全体の権限変更を防ぐ。"""
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert '[[ "${value}" != "/" ]]' in setup


def test_public_tls_installs_a_certbot_deploy_hook() -> None:
    """証明書更新後に Apache を再読み込みする hook を配備する。"""
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "renewal-hooks/deploy/relink-reference-lab-apache-reload" in setup
    assert "/usr/bin/systemctl reload apache2" in setup
    assert "Managed by relink-reference-lab scripts/setup-linux.sh" in setup
    assert "管理対象外の Certbot deploy hook を上書きしません" in setup


def test_public_tls_restricts_execution_and_applies_hardening() -> None:
    """public mode は実行面を制限し、Resolver Native hardening を再利用する。"""
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert 'EXECUTION_ALLOWLIST="${EXECUTION_ALLOWLIST:-local}"' in setup
    assert 'Require local' in setup
    assert 'Require ip 127.0.0.1 ${EXECUTION_ALLOWLIST//,/ }' in setup
    assert 'SetEnv RELINK_ENV $(if [[ "${TLS_MODE}" == "public" ]]' in setup
    assert "ServerTokens Prod" in setup
    assert "ServerSignature Off" in setup
    assert "TraceEnable Off" in setup
    assert "expose_php = Off" in setup
    assert 'Strict-Transport-Security "max-age=31536000"' in setup
    assert "--require-hsts" in setup


def test_setup_rejects_zero_timeout_and_unrestricted_allowlist() -> None:
    """実行待機時間と公開実行面の入力検査が仕様と一致する。"""
    setup = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "value + 0 > 0" in setup
    assert "Execution allowlist に全ネットワークを許可する /0 は指定できません" in setup
