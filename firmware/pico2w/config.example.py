# firmware/pico2w/config.example.py
"""Pico 2 W 用設定例。コピーして config.py として編集する。"""

# Wi-Fi の SSID とパスワードを設定する。
WIFI_SSID = "your-wifi-ssid"
WIFI_PASSWORD = "your-wifi-password"

# Gateway の /device までの公開 URL を設定する。
GATEWAY_URL = "https://example.invalid/device"
DEVICE_ID = "pico2w-01"

# ネットワーク障害時の polling 間隔と HTTP timeout（秒）。
POLL_INTERVAL_SECONDS = 1
HTTP_TIMEOUT_SECONDS = 10
