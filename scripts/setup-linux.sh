#!/usr/bin/env bash
# scripts/setup-linux.sh
# Debian/Ubuntu 系ホストへ Resolver と Reference Lab を一括構築する。

set -Eeuo pipefail

# Lab が検証済みとして固定する外部 Resolver の取得元と revision。
readonly DEFAULT_RESOLVER_REPOSITORY="https://github.com/ranmaru50/relink-resolver.git"
readonly DEFAULT_RESOLVER_REVISION="b790ac9770975b39b488a104125dc6510e1f54bf"
# RELink Web Runtime v0.1.0 の既存 download script と同じ検証値。
readonly RUNTIME_SHA256="f18d739edabc23285abd5fb64fcc056f17aaf480ddd1e0b6bed1702f8aab9e46"
readonly RESOLVER_SITE_PATH="/etc/apache2/sites-available/relink-resolver.conf"
readonly LAB_SITE_PATH="/etc/apache2/sites-available/relink-reference-lab.conf"
readonly RESOLVER_SITE_LINK="/etc/apache2/sites-enabled/relink-resolver.conf"
readonly LAB_SITE_LINK="/etc/apache2/sites-enabled/relink-reference-lab.conf"
readonly APACHE_HARDENING_CONF_NAME="zz-relink-reference-lab-hardening"
readonly APACHE_HARDENING_CONF_PATH="/etc/apache2/conf-available/${APACHE_HARDENING_CONF_NAME}.conf"
readonly APACHE_HARDENING_CONF_LINK="/etc/apache2/conf-enabled/${APACHE_HARDENING_CONF_NAME}.conf"
readonly CERTBOT_HOOK_PATH="/etc/letsencrypt/renewal-hooks/deploy/relink-reference-lab-apache-reload"
readonly SETUP_MARKER="# Managed by relink-reference-lab scripts/setup-linux.sh"

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LAB_ROOT="$(cd -- "${SCRIPT_DIRECTORY}/.." && pwd)"

# 環境変数で同じ値を指定でき、CLI 引数が環境変数より優先される。
RESOLVER_HOST="${RESOLVER_HOST:-resolver.relink.test}"
LAB_HOST="${LAB_HOST:-lab.relink.test}"
ANCHOR_UUID="${ANCHOR_UUID:-550e8400-e29b-41d4-a716-446655440000}"
DEVICE_ID="${DEVICE_ID:-pico2w-01}"
DEVICE_COMMAND_TIMEOUT="${DEVICE_COMMAND_TIMEOUT:-8}"
RESOLVER_INSTALL_PATH="${RESOLVER_INSTALL_PATH:-/opt/relink/relink-resolver}"
RESOLVER_DATA_PATH="${RESOLVER_DATA_PATH:-/var/lib/relink-resolver}"
LAB_DATA_PATH="${LAB_DATA_PATH:-/var/lib/relink-reference-lab}"
RESOLVER_REPOSITORY="${RESOLVER_REPOSITORY:-${DEFAULT_RESOLVER_REPOSITORY}}"
RESOLVER_REVISION="${RESOLVER_REVISION:-${DEFAULT_RESOLVER_REVISION}}"
TLS_MODE="${TLS_MODE:-local-ca}"
TLS_CERTIFICATE_FILE="${TLS_CERTIFICATE_FILE:-}"
TLS_KEY_FILE="${TLS_KEY_FILE:-}"
RESOLVER_ADMIN_USERNAME="${RESOLVER_ADMIN_USERNAME:-admin}"
EXECUTION_ALLOWLIST="${EXECUTION_ALLOWLIST:-local}"

WORK_DIRECTORY=""
ROLLBACK_ACTIVE=0
RESOLVER_SITE_WAS_ENABLED=0
LAB_SITE_WAS_ENABLED=0
APACHE_WAS_ACTIVE=0
CERTBOT_HOOK_CHANGE_ACTIVE=0
CERTBOT_HOOK_WAS_PRESENT=0
APACHE_HARDENING_WAS_ENABLED=0
PHP_SECURITY_CONFIG_PATH=""

usage() {
    cat <<'EOF'
使用方法:
  sudo ./scripts/setup-linux.sh [オプション]

主なオプション:
  --resolver-host HOST          Resolver のホスト名
  --lab-host HOST               Lab のホスト名
  --anchor-uuid UUID            初期登録する Anchor UUID
  --device-id ID                Pico と Lab で共有する device ID
  --device-command-timeout SEC  Capability command の待機秒数
  --resolver-install-path PATH  外部 Resolver checkout の配置先
  --resolver-data-path PATH     Resolver SQLite のデータディレクトリ
  --lab-data-path PATH          Lab SQLite のデータディレクトリ
  --resolver-repository URL     Resolver の公式 Git repository
  --resolver-revision SHA       取得する固定 Resolver revision
  --tls-mode MODE               local-ca（既定）または public
  --certificate-file PATH       public mode の証明書 chain
  --certificate-key-file PATH   public mode の秘密鍵
  --resolver-admin-username ID  Resolver 管理ユーザー名
  --execution-allowlist LIST    public mode の /api/ と /device/ の許可元（local または CIDRをカンマ区切り）
  --help                        このヘルプを表示

local-ca は実験専用 CA を生成し、VM 自身の検証だけで信頼します。通常の Web PKI と
同等ではありません。公開環境では public mode と信頼済み証明書を使用してください。
EOF
}

log() {
    printf '[setup] %s\n' "$*"
}

fail() {
    printf '[setup] ERROR: %s\n' "$*" >&2
    exit 1
}

require_option_value() {
    local option_name="$1"
    local option_value="${2:-}"
    [[ -n "${option_value}" ]] || fail "${option_name} には値が必要です。"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resolver-host)
            require_option_value "$1" "${2:-}"
            RESOLVER_HOST="$2"
            shift 2
            ;;
        --lab-host)
            require_option_value "$1" "${2:-}"
            LAB_HOST="$2"
            shift 2
            ;;
        --anchor-uuid)
            require_option_value "$1" "${2:-}"
            ANCHOR_UUID="$2"
            shift 2
            ;;
        --device-id)
            require_option_value "$1" "${2:-}"
            DEVICE_ID="$2"
            shift 2
            ;;
        --device-command-timeout)
            require_option_value "$1" "${2:-}"
            DEVICE_COMMAND_TIMEOUT="$2"
            shift 2
            ;;
        --resolver-install-path)
            require_option_value "$1" "${2:-}"
            RESOLVER_INSTALL_PATH="$2"
            shift 2
            ;;
        --resolver-data-path)
            require_option_value "$1" "${2:-}"
            RESOLVER_DATA_PATH="$2"
            shift 2
            ;;
        --lab-data-path)
            require_option_value "$1" "${2:-}"
            LAB_DATA_PATH="$2"
            shift 2
            ;;
        --resolver-repository)
            require_option_value "$1" "${2:-}"
            RESOLVER_REPOSITORY="$2"
            shift 2
            ;;
        --resolver-revision)
            require_option_value "$1" "${2:-}"
            RESOLVER_REVISION="$2"
            shift 2
            ;;
        --tls-mode)
            require_option_value "$1" "${2:-}"
            TLS_MODE="$2"
            shift 2
            ;;
        --certificate-file)
            require_option_value "$1" "${2:-}"
            TLS_CERTIFICATE_FILE="$2"
            shift 2
            ;;
        --certificate-key-file)
            require_option_value "$1" "${2:-}"
            TLS_KEY_FILE="$2"
            shift 2
            ;;
        --resolver-admin-username)
            require_option_value "$1" "${2:-}"
            RESOLVER_ADMIN_USERNAME="$2"
            shift 2
            ;;
        --execution-allowlist)
            require_option_value "$1" "${2:-}"
            EXECUTION_ALLOWLIST="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "未対応のオプションです: $1"
            ;;
    esac
done

validate_host() {
    local value="$1"
    local label="$2"
    [[ "${value}" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] \
        || fail "${label} がホスト名として不正です: ${value}"
}

validate_absolute_path() {
    local value="$1"
    local label="$2"
    [[ "${value}" == /* ]] || fail "${label} は絶対パスで指定してください。"
    [[ "${value}" != "/" ]] || fail "${label} にルートディレクトリは指定できません。"
    [[ "${value}" != *$'\n'* && "${value}" != *$'\r'* && "${value}" != *'"'* ]] \
        || fail "${label} に使用できない文字が含まれています。"
}

validate_inputs() {
    validate_host "${RESOLVER_HOST}" "Resolver host"
    validate_host "${LAB_HOST}" "Lab host"
    [[ "${RESOLVER_HOST,,}" != "${LAB_HOST,,}" ]] \
        || fail "Resolver host と Lab host は別のホスト名にしてください。"
    [[ "${ANCHOR_UUID}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] \
        || fail "Anchor UUID の形式が不正です。"
    [[ "${DEVICE_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] \
        || fail "Device ID の形式が不正です。"
    [[ "${DEVICE_COMMAND_TIMEOUT}" =~ ^[0-9]+([.][0-9]+)?$ ]] \
        || fail "Device command timeout は正の数で指定してください。"
    awk -v value="${DEVICE_COMMAND_TIMEOUT}" 'BEGIN { exit !(value + 0 > 0) }' \
        || fail "Device command timeout は 0 より大きい数で指定してください。"
    [[ "${RESOLVER_ADMIN_USERNAME}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] \
        || fail "Resolver 管理ユーザー名の形式が不正です。"
    [[ "${RESOLVER_REVISION}" =~ ^[0-9a-fA-F]{40}$ ]] \
        || fail "Resolver revision は完全な 40 桁 commit SHA で指定してください。"
    validate_absolute_path "${RESOLVER_INSTALL_PATH}" "Resolver installation path"
    validate_absolute_path "${RESOLVER_DATA_PATH}" "Resolver data path"
    validate_absolute_path "${LAB_DATA_PATH}" "Lab data path"
    if [[ "${EXECUTION_ALLOWLIST}" != "local" ]]; then
        [[ -n "${EXECUTION_ALLOWLIST}" ]] \
            || fail "Execution allowlist は local または CIDR のリストで指定してください。"
        local network
        local -a execution_networks
        IFS=',' read -r -a execution_networks <<< "${EXECUTION_ALLOWLIST}"
        ((${#execution_networks[@]} > 0)) \
            || fail "Execution allowlist は local または CIDR のリストで指定してください。"
        for network in "${execution_networks[@]}"; do
            [[ "${network}" =~ ^[0-9A-Fa-f:.]+(/[0-9]{1,3})?$ ]] \
                || fail "Execution allowlist の CIDR が不正です: ${network}"
            [[ "${network}" != */0 ]] \
                || fail "Execution allowlist に全ネットワークを許可する /0 は指定できません。"
        done
    fi
    [[ "${TLS_MODE}" == "local-ca" || "${TLS_MODE}" == "public" ]] \
        || fail "TLS mode は local-ca または public です。"
    if [[ "${TLS_MODE}" == "public" ]]; then
        [[ -n "${TLS_CERTIFICATE_FILE}" && -n "${TLS_KEY_FILE}" ]] \
            || fail "public mode では証明書と秘密鍵の指定が必要です。"
        validate_absolute_path "${TLS_CERTIFICATE_FILE}" "Certificate file"
        validate_absolute_path "${TLS_KEY_FILE}" "Certificate key file"
    fi
}

validate_supported_system() {
    [[ -r /etc/os-release ]] || fail "Linux distribution を判別できません。"
    # shellcheck disable=SC1091
    source /etc/os-release
    case "${ID:-}" in
        ubuntu)
            dpkg --compare-versions "${VERSION_ID:-0}" ge "24.04" \
                || fail "Ubuntu 24.04 以降だけをサポートします。"
            ;;
        debian)
            dpkg --compare-versions "${VERSION_ID:-0}" ge "13" \
                || fail "Debian 13 以降だけをサポートします。"
            ;;
        *)
            fail "未対応の Linux distribution です: ${ID:-unknown}"
            ;;
    esac
}

restore_apache_state() {
    [[ "${ROLLBACK_ACTIVE}" -eq 1 ]] || return 0
    log "失敗した Apache site 変更をロールバックします。"
    if [[ -f "${WORK_DIRECTORY}/resolver-site.backup" ]]; then
        cp -a "${WORK_DIRECTORY}/resolver-site.backup" "${RESOLVER_SITE_PATH}"
    else
        rm -f "${RESOLVER_SITE_PATH}"
    fi
    if [[ -f "${WORK_DIRECTORY}/lab-site.backup" ]]; then
        cp -a "${WORK_DIRECTORY}/lab-site.backup" "${LAB_SITE_PATH}"
    else
        rm -f "${LAB_SITE_PATH}"
    fi
    if [[ -f "${WORK_DIRECTORY}/apache-hardening.backup" ]]; then
        cp -a "${WORK_DIRECTORY}/apache-hardening.backup" "${APACHE_HARDENING_CONF_PATH}"
    else
        rm -f "${APACHE_HARDENING_CONF_PATH}"
    fi
    if [[ -n "${PHP_SECURITY_CONFIG_PATH}" ]]; then
        if [[ -f "${WORK_DIRECTORY}/php-security.backup" ]]; then
            cp -a "${WORK_DIRECTORY}/php-security.backup" "${PHP_SECURITY_CONFIG_PATH}"
        else
            rm -f "${PHP_SECURITY_CONFIG_PATH}"
        fi
    fi
    if [[ "${APACHE_HARDENING_WAS_ENABLED}" -eq 0 ]]; then
        a2disconf "${APACHE_HARDENING_CONF_NAME}" >/dev/null 2>&1 || true
    else
        a2enconf "${APACHE_HARDENING_CONF_NAME}" >/dev/null 2>&1 || true
    fi
    if [[ "${RESOLVER_SITE_WAS_ENABLED}" -eq 0 ]]; then
        a2dissite relink-resolver >/dev/null 2>&1 || true
    else
        a2ensite relink-resolver >/dev/null 2>&1 || true
    fi
    if [[ "${LAB_SITE_WAS_ENABLED}" -eq 0 ]]; then
        a2dissite relink-reference-lab >/dev/null 2>&1 || true
    else
        a2ensite relink-reference-lab >/dev/null 2>&1 || true
    fi
    if [[ -f "${WORK_DIRECTORY}/hosts.backup" ]]; then
        cp -a "${WORK_DIRECTORY}/hosts.backup" /etc/hosts
    fi
    if [[ "${APACHE_WAS_ACTIVE}" -eq 1 ]]; then
        if apache2ctl configtest >/dev/null 2>&1; then
            systemctl reload apache2 >/dev/null 2>&1 || true
        fi
    else
        systemctl stop apache2 >/dev/null 2>&1 || true
    fi
}

restore_certbot_hook() {
    [[ "${CERTBOT_HOOK_CHANGE_ACTIVE}" -eq 1 ]] || return 0
    log "失敗した Certbot deploy hook の変更をロールバックします。"
    if [[ "${CERTBOT_HOOK_WAS_PRESENT}" -eq 1 && -f "${WORK_DIRECTORY}/certbot-hook.backup" ]]; then
        cp -a "${WORK_DIRECTORY}/certbot-hook.backup" "${CERTBOT_HOOK_PATH}"
    else
        rm -f "${CERTBOT_HOOK_PATH}"
    fi
    CERTBOT_HOOK_CHANGE_ACTIVE=0
}

cleanup() {
    local status=$?
    if [[ "${status}" -ne 0 ]]; then
        restore_certbot_hook
        restore_apache_state
    fi
    if [[ -n "${WORK_DIRECTORY}" && -d "${WORK_DIRECTORY}" ]]; then
        rm -rf "${WORK_DIRECTORY}"
    fi
    exit "${status}"
}
trap cleanup EXIT

generate_local_certificate() {
    local tls_directory="/etc/relink-reference-lab/tls"
    local ca_key="${tls_directory}/development-ca.key"
    local ca_certificate="${tls_directory}/development-ca.crt"
    local server_key="${tls_directory}/relink-lab.key"
    local server_certificate="${tls_directory}/relink-lab.crt"
    local certificate_request="${WORK_DIRECTORY}/relink-lab.csr"
    local extension_file="${WORK_DIRECTORY}/relink-lab-extensions.cnf"

    install -d -o root -g root -m 0700 "${tls_directory}"
    if [[ -e "${ca_key}" || -e "${ca_certificate}" || -e "${server_key}" || -e "${server_certificate}" ]]; then
        [[ -f "${ca_key}" && -f "${ca_certificate}" && -f "${server_key}" && -f "${server_certificate}" ]] \
            || fail "開発 TLS ファイルが一部だけ存在します: ${tls_directory}"
        openssl x509 -checkend 86400 -noout -in "${server_certificate}" >/dev/null \
            || fail "開発証明書が失効済み、または 24 時間以内に失効します。"
        openssl x509 -checkhost "${RESOLVER_HOST}" -noout -in "${server_certificate}" >/dev/null \
            || fail "既存の開発証明書は Resolver host と一致しません。"
        openssl x509 -checkhost "${LAB_HOST}" -noout -in "${server_certificate}" >/dev/null \
            || fail "既存の開発証明書は Lab host と一致しません。"
    else
        log "実験専用 CA と HTTPS 証明書を生成します。"
        openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "${ca_key}"
        openssl req -x509 -new -sha256 -days 3650 -key "${ca_key}" \
            -subj "/CN=RELink Reference Lab Development CA" -out "${ca_certificate}"
        openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "${server_key}"
        openssl req -new -sha256 -key "${server_key}" \
            -subj "/CN=${LAB_HOST}" -out "${certificate_request}"
        cat >"${extension_file}" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:${RESOLVER_HOST},DNS:${LAB_HOST}
EOF
        openssl x509 -req -sha256 -days 825 -in "${certificate_request}" \
            -CA "${ca_certificate}" -CAkey "${ca_key}" -CAcreateserial \
            -extfile "${extension_file}" -out "${server_certificate}"
        chmod 0600 "${ca_key}" "${server_key}"
        chmod 0644 "${ca_certificate}" "${server_certificate}"
    fi

    TLS_CERTIFICATE_FILE="${server_certificate}"
    TLS_KEY_FILE="${server_key}"
    DEVELOPMENT_CA_FILE="${ca_certificate}"
}

install_certbot_deploy_hook() {
    # Certbot 更新後に Apache が新しい証明書を読み込む deploy hook を登録する。
    [[ "${TLS_MODE}" == "public" ]] || return 0
    local hook_path="${CERTBOT_HOOK_PATH}"
    local hook_file="${WORK_DIRECTORY}/certbot-deploy-hook"
    if [[ -e "${hook_path}" || -L "${hook_path}" ]]; then
        [[ -f "${hook_path}" && ! -L "${hook_path}" ]] \
            || fail "Certbot deploy hook は通常ファイル以外のため上書きしません: ${hook_path}"
        grep -Fxq "${SETUP_MARKER}" "${hook_path}" \
            || fail "管理対象外の Certbot deploy hook を上書きしません: ${hook_path}"
        cp -a "${hook_path}" "${WORK_DIRECTORY}/certbot-hook.backup"
        CERTBOT_HOOK_WAS_PRESENT=1
    fi
    CERTBOT_HOOK_CHANGE_ACTIVE=1
    cat >"${hook_file}" <<'EOF'
#!/usr/bin/env bash
# Managed by relink-reference-lab scripts/setup-linux.sh
# Certbot 更新後に Apache の証明書を再読み込みする。
set -Eeuo pipefail
/usr/sbin/apache2ctl configtest
/usr/bin/systemctl reload apache2
EOF
    install -d -o root -g root -m 0755 "$(dirname -- "${hook_path}")"
    install -o root -g root -m 0755 "${hook_file}" "${hook_path}"
}

acquire_resolver() {
    local parent_directory
    parent_directory="$(dirname -- "${RESOLVER_INSTALL_PATH}")"
    install -d -o root -g root -m 0755 "${parent_directory}"
    if [[ ! -e "${RESOLVER_INSTALL_PATH}" ]]; then
        log "外部 Resolver repository を取得します。"
        git clone --no-checkout "${RESOLVER_REPOSITORY}" "${RESOLVER_INSTALL_PATH}"
    else
        [[ -d "${RESOLVER_INSTALL_PATH}/.git" ]] \
            || fail "Resolver installation path は既存の Git checkout ではありません。"
        local existing_remote
        existing_remote="$(resolver_git remote get-url origin)"
        [[ "${existing_remote%.git}" == "${RESOLVER_REPOSITORY%.git}" ]] \
            || fail "既存 Resolver checkout の origin が指定 repository と一致しません。"
        [[ -z "$(resolver_git status --porcelain --untracked-files=normal)" ]] \
            || fail "既存 Resolver checkout に未コミット変更があります。"
    fi

    resolver_git fetch --depth 1 origin "${RESOLVER_REVISION}"
    resolver_git checkout --detach "${RESOLVER_REVISION}"
    local actual_revision
    actual_revision="$(resolver_git rev-parse HEAD)"
    [[ "${actual_revision}" == "${RESOLVER_REVISION}" ]] \
        || fail "Resolver revision の固定に失敗しました。"
    log "Resolver revision: ${actual_revision}"
}

resolver_git() {
    # root 実行でも既存の互換 checkout を安全に検査できるよう対象だけを許可する。
    git -c safe.directory="${RESOLVER_INSTALL_PATH}" -C "${RESOLVER_INSTALL_PATH}" "$@"
}

write_apache_sites() {
    local resolver_config="${WORK_DIRECTORY}/relink-resolver.conf"
    local lab_config="${WORK_DIRECTORY}/relink-reference-lab.conf"
    local hardening_config="${WORK_DIRECTORY}/relink-reference-lab-hardening.conf"
    local resolver_database="${RESOLVER_DATA_PATH}/resolver.sqlite"
    local execution_require="Require all granted"
    local hsts_header=""
    local resolver_environment="development"

    if [[ "${TLS_MODE}" == "public" ]]; then
        resolver_environment="production"
        if [[ "${EXECUTION_ALLOWLIST}" == "local" ]]; then
            execution_require="Require local"
        else
            execution_require="Require ip 127.0.0.1 ${EXECUTION_ALLOWLIST//,/ }"
        fi
        hsts_header='    Header always set Strict-Transport-Security "max-age=31536000"'
    fi

    cat >"${hardening_config}" <<EOF
${SETUP_MARKER}
# Resolver Native profile と同等の Apache/PHP hardening。
ServerTokens Prod
ServerSignature Off
TraceEnable Off
EOF

    local php_security_config="${WORK_DIRECTORY}/relink-reference-lab-security.ini"
    cat >"${php_security_config}" <<EOF
; ${SETUP_MARKER}
; Resolver Native profile の deploy/php-security.ini と同等の制限。
expose_php = Off
post_max_size = 64K
max_input_vars = 32
arg_separator.input = "&"
max_input_time = 10
max_execution_time = 15
memory_limit = 128M
EOF
    local php_apache_conf_dir
    php_apache_conf_dir="/etc/php/$(php -r 'echo PHP_MAJOR_VERSION . "." . PHP_MINOR_VERSION;')/apache2/conf.d"
    PHP_SECURITY_CONFIG_PATH="${php_apache_conf_dir}/99-relink-reference-lab-security.ini"

    cat >"${resolver_config}" <<EOF
${SETUP_MARKER}
<VirtualHost *:443>
    ServerName ${RESOLVER_HOST}
    DocumentRoot "${RESOLVER_INSTALL_PATH}/public"

    SSLEngine on
    SSLCertificateFile "${TLS_CERTIFICATE_FILE}"
    SSLCertificateKeyFile "${TLS_KEY_FILE}"

    SetEnv RELINK_ENV ${resolver_environment}
    SetEnv RELINK_ADMIN_USERNAME "${RESOLVER_ADMIN_USERNAME}"
    SetEnv RELINK_ADMIN_PASSWORD "${RESOLVER_ADMIN_PASSWORD}"
    SetEnv RELINK_ADMIN_ALLOW_HTTP 0
    SetEnv RELINK_DATA_DIR "${RESOLVER_DATA_PATH}"
    SetEnv RELINK_DB_PATH "${resolver_database}"
    SetEnv RELINK_SERVICE_PREFIX /relink

    LimitRequestBody 65536
    LimitRequestFields 50
    LimitRequestFieldSize 8190
    RequestReadTimeout header=10-20,MinRate=500 body=10,MinRate=500
${hsts_header}

    <Directory "${RESOLVER_INSTALL_PATH}/public">
        AllowOverride All
        Require all granted
    </Directory>
    <Files "admin.php">
        Require local
    </Files>

    Header always set X-Content-Type-Options "nosniff"
    ErrorLog \${APACHE_LOG_DIR}/relink-resolver-error.log
    CustomLog \${APACHE_LOG_DIR}/relink-resolver-access.log combined
</VirtualHost>
EOF

    cat >"${lab_config}" <<EOF
${SETUP_MARKER}
<VirtualHost *:443>
    ServerName ${LAB_HOST}
    DocumentRoot "${LAB_ROOT}/public"

    SSLEngine on
    SSLCertificateFile "${TLS_CERTIFICATE_FILE}"
    SSLCertificateKeyFile "${TLS_KEY_FILE}"

    SetEnv LAB_DB_PATH "${LAB_DATA_PATH}/lab.sqlite"
    SetEnv DEVICE_ID "${DEVICE_ID}"
    SetEnv DEVICE_COMMAND_TIMEOUT "${DEVICE_COMMAND_TIMEOUT}"
    SetEnv RESOLVER_BASE_URL "https://${RESOLVER_HOST}"
    SetEnv ANCHOR_UUID "${ANCHOR_UUID}"
    LimitRequestBody 65536
    LimitRequestFields 50
    LimitRequestFieldSize 8190
    RequestReadTimeout header=10-20,MinRate=500 body=10,MinRate=500
${hsts_header}

    <Directory "${LAB_ROOT}/public">
        AllowOverride All
        Require all granted
    </Directory>
    <LocationMatch "^/(api|device)(/|$)">
        ${execution_require}
    </LocationMatch>

    Header always set X-Content-Type-Options "nosniff"
    <FilesMatch "\.(arxml|html|js)$">
        Header set Access-Control-Allow-Origin "*"
        Header set Access-Control-Allow-Methods "GET, OPTIONS"
        Header set Referrer-Policy "no-referrer"
    </FilesMatch>
    ErrorLog \${APACHE_LOG_DIR}/relink-reference-lab-error.log
    CustomLog \${APACHE_LOG_DIR}/relink-reference-lab-access.log combined
</VirtualHost>
EOF

    for site_path in "${RESOLVER_SITE_PATH}" "${LAB_SITE_PATH}"; do
        if [[ -e "${site_path}" ]] && ! grep -Fxq "${SETUP_MARKER}" "${site_path}"; then
            fail "管理対象外の Apache site を上書きしません: ${site_path}"
        fi
    done
    if [[ -e "${APACHE_HARDENING_CONF_PATH}" ]] && ! grep -Fxq "${SETUP_MARKER}" "${APACHE_HARDENING_CONF_PATH}"; then
        fail "管理対象外の Apache hardening 設定を上書きしません: ${APACHE_HARDENING_CONF_PATH}"
    fi
    if [[ -e "${PHP_SECURITY_CONFIG_PATH}" ]] && ! grep -Fq "${SETUP_MARKER}" "${PHP_SECURITY_CONFIG_PATH}"; then
        fail "管理対象外の PHP security 設定を上書きしません: ${PHP_SECURITY_CONFIG_PATH}"
    fi

    [[ -L "${RESOLVER_SITE_LINK}" ]] && RESOLVER_SITE_WAS_ENABLED=1
    [[ -L "${LAB_SITE_LINK}" ]] && LAB_SITE_WAS_ENABLED=1
    [[ -f "${RESOLVER_SITE_PATH}" ]] \
        && cp -a "${RESOLVER_SITE_PATH}" "${WORK_DIRECTORY}/resolver-site.backup"
    [[ -f "${LAB_SITE_PATH}" ]] \
        && cp -a "${LAB_SITE_PATH}" "${WORK_DIRECTORY}/lab-site.backup"
    [[ -f "${APACHE_HARDENING_CONF_PATH}" ]] \
        && cp -a "${APACHE_HARDENING_CONF_PATH}" "${WORK_DIRECTORY}/apache-hardening.backup"
    [[ -f "${PHP_SECURITY_CONFIG_PATH}" ]] \
        && cp -a "${PHP_SECURITY_CONFIG_PATH}" "${WORK_DIRECTORY}/php-security.backup"
    [[ -L "${APACHE_HARDENING_CONF_LINK}" ]] && APACHE_HARDENING_WAS_ENABLED=1
    cp -a /etc/hosts "${WORK_DIRECTORY}/hosts.backup"
    ROLLBACK_ACTIVE=1
    systemctl is-active --quiet apache2 && APACHE_WAS_ACTIVE=1

    install -d -o root -g root -m 0755 "${php_apache_conf_dir}"
    install -o root -g root -m 0644 "${hardening_config}" "${APACHE_HARDENING_CONF_PATH}"
    install -o root -g root -m 0644 "${php_security_config}" "${PHP_SECURITY_CONFIG_PATH}"
    install -o root -g root -m 0600 "${resolver_config}" "${RESOLVER_SITE_PATH}"
    install -o root -g root -m 0644 "${lab_config}" "${LAB_SITE_PATH}"

    # VM 内の end-state check と管理画面用に限定した名前解決を冪等更新する。
    awk '!/# relink-reference-lab setup-linux$/' /etc/hosts >"${WORK_DIRECTORY}/hosts"
    printf '127.0.0.1 %s %s # relink-reference-lab setup-linux\n' \
        "${RESOLVER_HOST}" "${LAB_HOST}" >>"${WORK_DIRECTORY}/hosts"
    install -o root -g root -m 0644 "${WORK_DIRECTORY}/hosts" /etc/hosts

    a2enmod env rewrite headers reqtimeout ssl >/dev/null
    a2enconf "${APACHE_HARDENING_CONF_NAME}" >/dev/null
    a2ensite relink-resolver relink-reference-lab >/dev/null
    apache2ctl configtest
    if systemctl is-active --quiet apache2; then
        systemctl reload apache2
    else
        systemctl enable --now apache2
    fi
}

[[ "$(id -u)" -eq 0 ]] || fail "root 権限で実行してください: sudo ./scripts/setup-linux.sh"
validate_inputs
validate_supported_system
WORK_DIRECTORY="$(mktemp -d /tmp/relink-reference-lab-setup.XXXXXX)"

log "server package をインストールします。"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    apache2 ca-certificates composer curl git libapache2-mod-php openssl php php-cli \
    php-curl php-sqlite3 python3 sqlite3

php -r 'exit(version_compare(PHP_VERSION, "8.3.0", ">=") ? 0 : 1);' \
    || fail "Resolver には PHP 8.3 以上が必要です。"
php -r 'exit(extension_loaded("pdo_sqlite") ? 0 : 1);' \
    || fail "PHP pdo_sqlite extension が有効ではありません。"
runuser -u www-data -- test -r "${LAB_ROOT}/public/index.html" \
    || fail "Apache user が Lab clone を読めません。clone を /opt/relink 等へ移動してください。"

RESOLVER_INSTALL_PATH="$(realpath -m "${RESOLVER_INSTALL_PATH}")"
RESOLVER_DATA_PATH="$(realpath -m "${RESOLVER_DATA_PATH}")"
LAB_DATA_PATH="$(realpath -m "${LAB_DATA_PATH}")"
[[ "${RESOLVER_DATA_PATH}" != "${RESOLVER_INSTALL_PATH}/public"* ]] \
    || fail "Resolver data path は Resolver DocumentRoot 外へ配置してください。"
[[ "${LAB_DATA_PATH}" != "${LAB_ROOT}/public"* ]] \
    || fail "Lab data path は Lab DocumentRoot 外へ配置してください。"

acquire_resolver

log "Composer の production dependency を準備します。"
composer install --working-dir="${RESOLVER_INSTALL_PATH}" \
    --no-dev --no-interaction --prefer-dist --classmap-authoritative
composer install --working-dir="${LAB_ROOT}" \
    --no-dev --no-interaction --prefer-dist --classmap-authoritative

log "RELink Web Runtime v0.1.0 を取得し SHA-256 を検証します。"
python3 "${SCRIPT_DIRECTORY}/download_runtime.py"

install -d -o www-data -g www-data -m 0770 "${RESOLVER_DATA_PATH}"
install -d -o www-data -g www-data -m 0770 "${LAB_DATA_PATH}"
RESOLVER_DATABASE_PATH="${RESOLVER_DATA_PATH}/resolver.sqlite"
LAB_DATABASE_PATH="${LAB_DATA_PATH}/lab.sqlite"

log "Resolver と Lab の SQLite schema を初期化します。"
runuser -u www-data -- env \
    RELINK_DATA_DIR="${RESOLVER_DATA_PATH}" \
    RELINK_DB_PATH="${RESOLVER_DATABASE_PATH}" \
    php "${RESOLVER_INSTALL_PATH}/bin/migrate.php"
runuser -u www-data -- env \
    LAB_DB_PATH="${LAB_DATABASE_PATH}" \
    php "${SCRIPT_DIRECTORY}/init_db.php"

DESCRIPTION_LOCATION="https://${LAB_HOST}/arxml/pico2w.arxml"
ENTITY_ID="https://${LAB_HOST}/entities/${DEVICE_ID}"
log "外部 Resolver の application service でサンプル Anchor を登録します。"
runuser -u www-data -- env \
    RESOLVER_PATH="${RESOLVER_INSTALL_PATH}" \
    RELINK_DATA_DIR="${RESOLVER_DATA_PATH}" \
    RELINK_DB_PATH="${RESOLVER_DATABASE_PATH}" \
    ANCHOR_UUID="${ANCHOR_UUID}" \
    DESCRIPTION_LOCATION="${DESCRIPTION_LOCATION}" \
    ENTITY_ID="${ENTITY_ID}" \
    php "${SCRIPT_DIRECTORY}/register_resolver.php"

install -d -o root -g root -m 0700 /etc/relink-reference-lab
RESOLVER_ADMIN_PASSWORD_PATH="/etc/relink-reference-lab/resolver-admin-password"
if [[ -f "${RESOLVER_ADMIN_PASSWORD_PATH}" ]]; then
    RESOLVER_ADMIN_PASSWORD="$(<"${RESOLVER_ADMIN_PASSWORD_PATH}")"
    [[ -n "${RESOLVER_ADMIN_PASSWORD}" && "${RESOLVER_ADMIN_PASSWORD}" != *'"'* ]] \
        || fail "既存 Resolver 管理パスワードファイルが不正です。"
else
    RESOLVER_ADMIN_PASSWORD="$(openssl rand -hex 24)"
    printf '%s\n' "${RESOLVER_ADMIN_PASSWORD}" >"${RESOLVER_ADMIN_PASSWORD_PATH}"
    chmod 0600 "${RESOLVER_ADMIN_PASSWORD_PATH}"
fi

DEVELOPMENT_CA_FILE=""
if [[ "${TLS_MODE}" == "local-ca" ]]; then
    generate_local_certificate
else
    [[ -r "${TLS_CERTIFICATE_FILE}" && -r "${TLS_KEY_FILE}" ]] \
        || fail "public TLS 証明書または秘密鍵を読み込めません。"
    openssl x509 -checkend 86400 -noout -in "${TLS_CERTIFICATE_FILE}" >/dev/null \
        || fail "public TLS 証明書が失効済み、または 24 時間以内に失効します。"
    openssl x509 -checkhost "${RESOLVER_HOST}" -noout -in "${TLS_CERTIFICATE_FILE}" >/dev/null \
        || fail "public TLS 証明書は Resolver host をカバーしていません。"
    openssl x509 -checkhost "${LAB_HOST}" -noout -in "${TLS_CERTIFICATE_FILE}" >/dev/null \
        || fail "public TLS 証明書は Lab host をカバーしていません。"
fi
install_certbot_deploy_hook

log "Resolver と Lab の Apache VirtualHost を構成します。"
write_apache_sites

log "Apache、Resolver、Lab、Runtime、SQLite の end-state check を実行します。"
acceptance_arguments=(
    --base-url "https://${LAB_HOST}"
    --device-id "${DEVICE_ID}"
    --resolver-base-url "https://${RESOLVER_HOST}"
    --anchor-uuid "${ANCHOR_UUID}"
    --expected-location "${DESCRIPTION_LOCATION}"
    --runtime-sha256 "${RUNTIME_SHA256}"
)
if [[ -n "${DEVELOPMENT_CA_FILE}" ]]; then
    acceptance_arguments+=(--ca-file "${DEVELOPMENT_CA_FILE}")
else
    acceptance_arguments+=(--require-hsts)
fi
python3 "${SCRIPT_DIRECTORY}/apache_acceptance.py" "${acceptance_arguments[@]}"
[[ "$(sqlite3 "${RESOLVER_DATABASE_PATH}" 'PRAGMA quick_check;')" == "ok" ]] \
    || fail "Resolver SQLite quick_check が失敗しました。"
[[ "$(sqlite3 "${LAB_DATABASE_PATH}" 'PRAGMA quick_check;')" == "ok" ]] \
    || fail "Lab SQLite quick_check が失敗しました。"
sqlite3 "${LAB_DATABASE_PATH}" \
    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='commands';" | grep -qx '1' \
    || fail "Lab command store を利用できません。"

ROLLBACK_ACTIVE=0
CERTBOT_HOOK_CHANGE_ACTIVE=0

printf '\nRELink Reference Lab setup completed.\n\n'
printf 'Resolver revision:\n  %s\n\n' "${RESOLVER_REVISION}"
printf 'Resolver:\n  https://%s\n\n' "${RESOLVER_HOST}"
printf 'Lab:\n  https://%s\n\n' "${LAB_HOST}"
printf 'Anchor:\n  https://%s/relink/%s\n\n' "${RESOLVER_HOST}" "${ANCHOR_UUID}"
printf 'AR-XML:\n  %s\n\n' "${DESCRIPTION_LOCATION}"
printf 'Device API base:\n  https://%s/device\n\n' "${LAB_HOST}"
if [[ "${TLS_MODE}" == "public" ]]; then
    printf 'Execution allowlist:\n  %s (localhost is always retained for acceptance)\n\n' "${EXECUTION_ALLOWLIST}"
fi
if [[ -n "${DEVELOPMENT_CA_FILE}" ]]; then
    printf 'Development CA (local experiment only):\n  %s\n\n' "${DEVELOPMENT_CA_FILE}"
fi
printf 'LAN client hosts entry:\n  <server-ip> %s %s\n\n' "${RESOLVER_HOST}" "${LAB_HOST}"
printf '%s\n' \
    'Next steps:' \
    '1. Trust the development CA on the test client only, or use public Web PKI.' \
    '2. Configure Pico Wi-Fi.' \
    '3. Set Pico GATEWAY_URL / DEVICE_ID.' \
    '4. Copy firmware to Pico.' \
    '5. Open the Lab Web UI and explicitly invoke a Capability.'
