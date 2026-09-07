// public/app.js
// Web Runtime を使って Entity を発見し、ユーザー操作だけで Capability を呼び出す。

import { ARRuntime } from "./runtime-loader.js";

const anchorInput = document.querySelector("#anchor-url");
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

function setStatus(message, kind = "") {
  status.textContent = message;
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
    throw new Error(`Capability が見つかりません: ${localId}`);
  }

  const invocation = await capability.invoke(inputs, { accept: "application/json" });
  result.textContent = JSON.stringify(invocation.values, null, 2);
  setStatus(`${localId} の実行に成功しました。`, "success");
}

async function loadEntity() {
  setControlsEnabled(false);
  entityPanel.hidden = true;
  result.textContent = "";
  setStatus("Entity と AR-XML を読み込んでいます…");

  try {
    const runtime = new ARRuntime();
    runtimeDocument = await runtime.load(new URL(anchorInput.value, window.location.href).href);
    const capabilities = runtimeDocument.capabilities.map((capability) => capability.localId);
    entityTitle.textContent = runtimeDocument.category ?? "RELink Entity";
    capabilityList.textContent = capabilities.join(", ");
    entityPanel.hidden = false;
    setControlsEnabled(Boolean(runtimeDocument.getCapability("light") && runtimeDocument.getCapability("temperature")));
    setStatus(`ロード成功: ${runtimeDocument.url}`, "success");
  } catch (error) {
    setStatus(`ロードに失敗しました: ${error.message}`, "error");
  }
}

async function handleInvocation(action) {
  setControlsEnabled(false);
  setStatus(`${action} を実行しています…`);
  try {
    if (action === "light-on") await invokeCapability("light", { on: true });
    if (action === "light-off") await invokeCapability("light", { on: false });
    if (action === "temperature") await invokeCapability("temperature");
  } catch (error) {
    setStatus(`実行に失敗しました: ${error.message}`, "error");
  } finally {
    setControlsEnabled(Boolean(runtimeDocument));
  }
}

loadButton.addEventListener("click", loadEntity);
document.querySelector("#light-on").addEventListener("click", () => handleInvocation("light-on"));
document.querySelector("#light-off").addEventListener("click", () => handleInvocation("light-off"));
document.querySelector("#temperature-read").addEventListener("click", () => handleInvocation("temperature"));

setControlsEnabled(false);
