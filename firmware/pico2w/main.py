# firmware/pico2w/main.py
"""Pico 2 W の outbound-only RELink lab device session。"""

import json
import time

import machine
import network

try:
    import urequests as requests
except ImportError:
    import requests

try:
    import config
except ImportError:
    raise RuntimeError("config.py を config.example.py から作成してください")


# RP2350 内部温度 ADC の変換に使う基準値。室温センサー校正値ではない。
TEMP_ADC_CHANNEL = 4
TEMP_REFERENCE_VOLTAGE = 0.706
TEMP_SLOPE = 0.001721
MAX_BACKOFF_SECONDS = 30


def gateway_url(path):
    """Gateway の /device base URL に path を結合する。"""
    return config.GATEWAY_URL.rstrip("/") + "/" + path.lstrip("/")


def connect_wifi():
    """Wi-Fi 接続を bounded wait で確立し、失敗時は外側へ例外を返す。"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        deadline = time.ticks_add(
            time.ticks_ms(), config.WIFI_CONNECT_TIMEOUT_SECONDS * 1000
        )
        while not wlan.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                wlan.disconnect()
                raise RuntimeError("Wi-Fi connection timed out")
            time.sleep_ms(250)
    return wlan


def response_json(response):
    """HTTP response の JSON body を読み、必ず response を閉じる。"""
    try:
        if response.status_code != 200:
            raise RuntimeError("HTTP status: " + str(response.status_code))
        return response.json()
    finally:
        response.close()


def read_temperature():
    """RP2350 内部温度を Celsius の数値として読み取る。"""
    adc = machine.ADC(TEMP_ADC_CHANNEL)
    voltage = adc.read_u16() * 3.3 / 65535
    return round(27 - (voltage - TEMP_REFERENCE_VOLTAGE) / TEMP_SLOPE, 2)


def execute_command(command):
    """定義済みの二つの lab command だけを実行する。"""
    action = command.get("action")
    inputs = command.get("inputs", {})
    if action == "light.setState" and isinstance(inputs.get("on"), bool):
        machine.Pin("LED", machine.Pin.OUT).value(1 if inputs["on"] else 0)
        return {"state": inputs["on"]}
    if action == "temperature.read" and inputs == {}:
        return {"temperature": read_temperature()}
    raise RuntimeError("unsupported lab command")


def poll_once():
    """command を一件取得して実行し、相関 ID 付き result を返す。"""
    response = requests.get(
        gateway_url("commands") + "?device_id=" + config.DEVICE_ID,
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code == 204:
        response.close()
        return
    command = response_json(response)
    command_id = command.get("id")
    if not isinstance(command_id, str):
        raise RuntimeError("command id is missing")
    try:
        values = execute_command(command)
        payload = {"device_id": config.DEVICE_ID, "ok": True, "values": values}
    except Exception as error:
        payload = {"device_id": config.DEVICE_ID, "ok": False, "error": str(error)}
    result_response = requests.post(
        gateway_url("results/") + command_id,
        data=json.dumps(payload),
        # Result callback の失敗を外側の reconnect/backoff へ伝える。
        headers={"Content-Type": "application/json"},
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    try:
        if result_response.status_code != 200:
            raise RuntimeError("result callback HTTP status: " + str(result_response.status_code))
    finally:
        result_response.close()


def run():
    """Wi-Fi 接続、polling、指数バックオフによる再接続を繰り返す。"""
    backoff = 1
    while True:
        try:
            connect_wifi()
            poll_once()
            backoff = 1
            time.sleep(config.POLL_INTERVAL_SECONDS)
        except Exception:
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


run()
