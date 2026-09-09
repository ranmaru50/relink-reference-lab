// public/app.js
// Web Runtime を使って Entity を発見し、ユーザー操作だけで Capability を呼び出す。

import { ARRuntime } from "./runtime-loader.js";

const anchorInput = document.querySelector("#anchor-url");
const languageSelect = document.querySelector("#language-select");
const loadButton = document.querySelector("#load-button");
const status = document.querySelector("#status");
const entityPanel = document.querySelector("#entity-panel");
const entityTitle = document.querySelector("#entity-title");
const capabilityList = document.querySelector("#capability-list");
const result = document.querySelector("#result");
const controls = [
  document.querySelector("#light-on"),
  document.querySelector("#light-off"),
  document.querySelector("#temperature-read"),
];

let runtimeDocument;
let statusKey = "ready";
let statusArgs = {};
let statusKind = "";

const messages = {
  en: {
    title: "RELink Pico 2 W Reference Lab",
    heading: "RELink Pico 2 W Reference Lab",
    description: "Capabilities are not invoked while loading. Each operation runs only after you select a button.",
    languageLabel: "Language",
    english: "English",
    japanese: "日本語",
    anchorLabel: "Anchor URL",
    loadEntity: "Load Entity",
    ready: "Enter an Anchor URL.",
    loading: "Loading Entity and AR-XML…",
    loadSuccess: "Load succeeded: {url}",
    loadError: "Load failed: {error}",
    discoveredCapabilities: "Discovered Capabilities:",
    lightOn: "LED ON",
    lightOff: "LED OFF",
    readTemperature: "Read temperature",
    invoking: "Running {name}…",
    invocationSuccess: "{name} completed successfully.",
    invocationError: "Execution failed: {error}",
    missingCapability: "Capability not found: {id}",
  },
  ja: {
    title: "RELink Pico 2 W リファレンスラボ",
    heading: "RELink Pico 2 W リファレンスラボ",
    description: "ロード時にCapabilityは実行されません。各操作はボタンを押したときだけ実行されます。",
    languageLabel: "言語",
    english: "English",
    japanese: "日本語",
    anchorLabel: "Anchor URL",
    loadEntity: "Entityを読み込む",
    ready: "Anchor URLを入力してください。",
    loading: "EntityとAR-XMLを読み込んでいます…",
    loadSuccess: "ロード成功: {url}",
    loadError: "ロードに失敗しました: {error}",
    discoveredCapabilities: "検出されたCapability:",
    lightOn: "LEDをON",
    lightOff: "LEDをOFF",
    readTemperature: "温度を読み取る",
    invoking: "{name}を実行しています…",
    invocationSuccess: "{name}の実行に成功しました。",
    invocationError: "実行に失敗しました: {error}",
    missingCapability: "Capabilityが見つかりません: {id}",
  },
};

function getInitialLanguage() {
  try {
    const storedLanguage = window.localStorage.getItem("relink-language");
    if (storedLanguage && messages[storedLanguage]) return storedLanguage;
  } catch {
    // localStorage が利用できない環境ではブラウザー言語へフォールバックする。
  }
  return window.navigator.language?.toLowerCase().startsWith("ja") ? "ja" : "en";
}

let currentLanguage = getInitialLanguage();

function translate(key, args = {}) {
  const template = messages[currentLanguage][key] ?? messages.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => args[name] ?? `{${name}}`);
}

function applyLanguage(language) {
  if (!messages[language]) return;
  currentLanguage = language;
  document.documentElement.lang = language;
  document.title = translate("title");
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = translate(element.dataset.i18n);
  });
  if (languageSelect) languageSelect.value = language;
  try {
    window.localStorage.setItem("relink-language", language);
  } catch {
    // localStorage が利用できない環境でも、現在のページ内の切替は継続する。
  }
  setStatusKey(statusKey, statusArgs, statusKind);
}

function setStatusKey(key, args = {}, kind = "") {
  statusKey = key;
  statusArgs = args;
  statusKind = kind;
  status.textContent = translate(key, args);
  status.className = kind;
}

function setControlsEnabled(enabled) {
  controls.forEach((control) => {
    control.disabled = !enabled;
  });
}

async function invokeCapability(localId, inputs = {}) {
  const capability = runtimeDocument?.getCapability(localId);
  if (!capability) {
    throw new Error(translate("missingCapability", { id: localId }));
  }

  const invocation = await capability.invoke(inputs, { accept: "application/json" });
  result.textContent = JSON.stringify(invocation.values, null, 2);
  setStatusKey("invocationSuccess", { name: localId }, "success");
}

async function loadEntity() {
  setControlsEnabled(false);
  entityPanel.hidden = true;
  result.textContent = "";
  setStatusKey("loading");

  try {
    const runtime = new ARRuntime();
    runtimeDocument = await runtime.load(new URL(anchorInput.value, window.location.href).href);
    const capabilities = runtimeDocument.capabilities.map((capability) => capability.localId);
    entityTitle.textContent = runtimeDocument.category ?? "RELink Entity";
    capabilityList.textContent = capabilities.join(", ");
    entityPanel.hidden = false;
    setControlsEnabled(Boolean(runtimeDocument.getCapability("light") && runtimeDocument.getCapability("temperature")));
    setStatusKey("loadSuccess", { url: runtimeDocument.url }, "success");
  } catch (error) {
    setStatusKey("loadError", { error: error.message }, "error");
  }
}

async function handleInvocation(action) {
  setControlsEnabled(false);
  const actionNames = { "light-on": "lightOn", "light-off": "lightOff", temperature: "readTemperature" };
  setStatusKey("invoking", { name: translate(actionNames[action]) });
  try {
    if (action === "light-on") await invokeCapability("light", { on: true });
    if (action === "light-off") await invokeCapability("light", { on: false });
    if (action === "temperature") await invokeCapability("temperature");
  } catch (error) {
    setStatusKey("invocationError", { error: error.message }, "error");
  } finally {
    setControlsEnabled(Boolean(runtimeDocument));
  }
}

loadButton.addEventListener("click", loadEntity);
languageSelect?.addEventListener("change", () => applyLanguage(languageSelect.value));
document.querySelector("#light-on").addEventListener("click", () => handleInvocation("light-on"));
document.querySelector("#light-off").addEventListener("click", () => handleInvocation("light-off"));
document.querySelector("#temperature-read").addEventListener("click", () => handleInvocation("temperature"));

setControlsEnabled(false);
applyLanguage(currentLanguage);
