// public/app.js
// Draft 5 Entity を副作用なく評価し、明示操作だけを Capability invocation へ渡す。

import { ARRuntime, InMemorySemanticRegistry } from "./runtime-loader.js";

// Reference Lab が表示・評価する exact-versioned Profile の識別子。
const PROFILE_IDENTIFIER = "https://relink.dev/profiles/reference-lab/controller-monitor/1";
// ブラウザーから読み込む Reference Lab 用 Capability Contract fixture。
const CONTRACT_DEFINITIONS = [
  {
    path: "./definitions/contracts/temperature-read.contract.json",
    identifier: "https://relink.dev/capabilities/temperature/read/1",
  },
  {
    path: "./definitions/contracts/indicator-set.contract.json",
    identifier: "https://relink.dev/capabilities/indicator/set/1",
  },
];
// ブラウザーから読み込む Reference Lab 用 Profile fixture。
const PROFILE_DEFINITIONS = [
  {
    path: "./definitions/profiles/controller-monitor.profile.json",
    identifier: PROFILE_IDENTIFIER,
  },
];

const anchorInput = document.querySelector("#anchor-url");
const configuredAnchorUrl = globalThis.RELINK_LAB_CONFIG?.anchorUrl;
if (typeof configuredAnchorUrl === "string" && configuredAnchorUrl !== "") {
  anchorInput.value = configuredAnchorUrl;
}
const languageSelect = document.querySelector("#language-select");
const loadButton = document.querySelector("#load-button");
const status = document.querySelector("#status");
const entityPanel = document.querySelector("#entity-panel");
const entityTitle = document.querySelector("#entity-title");
const capabilityList = document.querySelector("#capability-list");
const claimStatus = document.querySelector("#profile-claim-status");
const definitionStatus = document.querySelector("#profile-definition-status");
const contractDefinitionStatus = document.querySelector("#profile-contract-status");
const conformanceStatus = document.querySelector("#profile-conformance-status");
const result = document.querySelector("#result");
const controls = {
  indicatorOn: document.querySelector("#light-on"),
  indicatorOff: document.querySelector("#light-off"),
  temperature: document.querySelector("#temperature-read"),
};

let runtimeDocument;
let semanticProfile;
let semanticContracts = [];
let statusKey = "ready";
let statusArgs = {};
let statusKind = "";

const messages = {
  en: {
    title: "RELink Pico 2 W Reference Lab",
    heading: "RELink Pico 2 W Reference Lab",
    description: "Loading and evaluation do not invoke Capabilities. Each physical operation runs only after you select a button.",
    languageLabel: "Language",
    english: "English",
    japanese: "日本語",
    anchorLabel: "Anchor URL",
    loadEntity: "Load Entity",
    ready: "Enter an Anchor URL.",
    loading: "Loading Entity and semantic definitions…",
    loadSuccess: "Load succeeded: {url}",
    loadError: "Load failed: {error}",
    discoveredCapabilities: "Discovered Capabilities:",
    profileClaimLabel: "Profile Claim:",
    profileDefinitionLabel: "Profile Definition:",
    contractDefinitionLabel: "Required Contract Definitions:",
    profileConformanceLabel: "Evaluated Conformance:",
    claimPresent: "present",
    claimAbsent: "absent",
    definitionResolved: "resolved",
    definitionUnresolved: "unresolved",
    lightOn: "LED ON",
    lightOff: "LED OFF",
    readTemperature: "Read controller temperature",
    invoking: "Running {name}…",
    invocationSuccess: "{name} completed successfully.",
    invocationError: "Execution failed: {error}",
    missingCapability: "Capability not found: {id}",
    ambiguousRoutes: "Invocation requires exactly one READY route; no route was selected.",
  },
  ja: {
    title: "RELink Pico 2 W リファレンスラボ",
    heading: "RELink Pico 2 W リファレンスラボ",
    description: "ロードと評価では Capability を実行しません。物理操作はボタンを押したときだけ実行されます。",
    languageLabel: "言語",
    english: "English",
    japanese: "日本語",
    anchorLabel: "Anchor URL",
    loadEntity: "Entityを読み込む",
    ready: "Anchor URLを入力してください。",
    loading: "Entityと意味定義を読み込んでいます…",
    loadSuccess: "ロード成功: {url}",
    loadError: "ロードに失敗しました: {error}",
    discoveredCapabilities: "検出されたCapability:",
    profileClaimLabel: "Profile Claim:",
    profileDefinitionLabel: "Profile定義:",
    contractDefinitionLabel: "必須Contract定義:",
    profileConformanceLabel: "評価済み適合性:",
    claimPresent: "あり",
    claimAbsent: "なし",
    definitionResolved: "解決済み",
    definitionUnresolved: "未解決",
    lightOn: "LEDをON",
    lightOff: "LEDをOFF",
    readTemperature: "コントローラー温度を読み取る",
    invoking: "{name}を実行しています…",
    invocationSuccess: "{name}の実行に成功しました。",
    invocationError: "実行に失敗しました: {error}",
    missingCapability: "Capabilityが見つかりません: {id}",
    ambiguousRoutes: "READYなrouteが1つに定まらないため、実行先を選択できません。",
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

function isSingleReadyRoute(localId) {
  const capability = runtimeDocument?.getCapability(localId);
  const readyRoutes = capability?.evaluation.routes.filter((route) => route.availability === "READY") ?? [];
  return readyRoutes.length === 1;
}

function setControlsEnabled(enabled) {
  controls.indicatorOn.disabled = !enabled || !isSingleReadyRoute("indicator");
  controls.indicatorOff.disabled = !enabled || !isSingleReadyRoute("indicator");
  controls.temperature.disabled = !enabled || !isSingleReadyRoute("controller-temperature");
}

async function fetchDefinition(definition) {
  try {
    const url = new URL(definition.path, window.location.href);
    const response = await fetch(url);
    if (!response.ok) return undefined;
    const value = await response.json();
    // Semantic Identifier は完全一致でのみ登録し、別バージョンへ代替しない。
    if (!value || value.identifier !== definition.identifier) return undefined;
    return value;
  } catch {
    // 定義の欠落や読み込み失敗は Runtime の UNRESOLVED 状態として表示する。
    return undefined;
  }
}

async function loadSemanticRegistry() {
  const [contracts, profiles] = await Promise.all([
    Promise.all(CONTRACT_DEFINITIONS.map(fetchDefinition)),
    Promise.all(PROFILE_DEFINITIONS.map(fetchDefinition)),
  ]);
  const resolvedContracts = contracts.filter((definition) => definition !== undefined);
  const resolvedProfiles = profiles.filter((definition) => definition !== undefined);
  return {
    registry: new InMemorySemanticRegistry(resolvedContracts, resolvedProfiles),
    contracts: resolvedContracts,
    profiles: resolvedProfiles,
  };
}

function renderProfileEvaluation() {
  const claimPresent = runtimeDocument.profileClaims.some((claim) => claim.href === PROFILE_IDENTIFIER);
  const evaluation = runtimeDocument.evaluateProfile(PROFILE_IDENTIFIER);
  const requiredContractIdentifiers = [
    ...(semanticProfile?.requiredCapabilities ?? []),
    ...(semanticProfile?.capabilityRequirements ?? [])
      .filter((requirement) => requirement.required !== false)
      .map((requirement) => requirement.contractIdentifier),
  ];
  const requiredContractsResolved = evaluation.resolution === "RESOLVED"
    && requiredContractIdentifiers.every((identifier) =>
      loadContractDefinitionCount(identifier) === 1,
    );
  claimStatus.textContent = translate(claimPresent ? "claimPresent" : "claimAbsent");
  definitionStatus.textContent = translate(
    evaluation.resolution === "RESOLVED" ? "definitionResolved" : "definitionUnresolved",
  );
  contractDefinitionStatus.textContent = translate(
    requiredContractsResolved ? "definitionResolved" : "definitionUnresolved",
  );
  const conformance = requiredContractsResolved ? evaluation.conformance : "UNDETERMINED";
  conformanceStatus.textContent = conformance;
  conformanceStatus.dataset.state = conformance;
}

function loadContractDefinitionCount(identifier) {
  return semanticContracts.filter((definition) => definition.identifier === identifier).length;
}

async function invokeCapability(localId, inputs = {}) {
  const capability = runtimeDocument?.getCapability(localId);
  if (!capability) {
    throw new Error(translate("missingCapability", { id: localId }));
  }
  const readyRoutes = capability.evaluation.routes.filter((route) => route.availability === "READY");
  if (readyRoutes.length !== 1) {
    throw new Error(translate("ambiguousRoutes"));
  }

  // Route を明示し、失敗時に別 route へ自動 retry しない。
  const invocation = await capability.invoke(inputs, {
    accept: "application/json",
    routeId: readyRoutes[0].routeId,
  });
  result.textContent = JSON.stringify(invocation.values, null, 2);
  setStatusKey("invocationSuccess", { name: localId }, "success");
}

async function loadEntity() {
  setControlsEnabled(false);
  entityPanel.hidden = true;
  result.textContent = "";
  setStatusKey("loading");

  try {
    const semanticRegistryDefinitions = await loadSemanticRegistry();
    semanticContracts = semanticRegistryDefinitions.contracts;
    semanticProfile = semanticRegistryDefinitions.profiles.find(
      (profile) => profile.identifier === PROFILE_IDENTIFIER,
    );
    const runtime = new ARRuntime({ semanticRegistry: semanticRegistryDefinitions.registry });
    runtimeDocument = await runtime.load(new URL(anchorInput.value, window.location.href).href);
    const capabilities = runtimeDocument.capabilities.map((capability) => capability.localId);
    entityTitle.textContent = runtimeDocument.category ?? "RELink Entity";
    capabilityList.textContent = capabilities.join(", ");
    renderProfileEvaluation();
    entityPanel.hidden = false;
    setControlsEnabled(true);
    setStatusKey("loadSuccess", { url: runtimeDocument.url }, "success");
  } catch (error) {
    runtimeDocument = undefined;
    semanticProfile = undefined;
    semanticContracts = [];
    setStatusKey("loadError", { error: error.message }, "error");
  }
}

async function handleInvocation(action) {
  setControlsEnabled(false);
  const actionNames = { "light-on": "lightOn", "light-off": "lightOff", temperature: "readTemperature" };
  setStatusKey("invoking", { name: translate(actionNames[action]) });
  try {
    if (action === "light-on") await invokeCapability("indicator", { on: true });
    if (action === "light-off") await invokeCapability("indicator", { on: false });
    if (action === "temperature") await invokeCapability("controller-temperature");
  } catch (error) {
    setStatusKey("invocationError", { error: error.message }, "error");
  } finally {
    setControlsEnabled(Boolean(runtimeDocument));
  }
}

loadButton.addEventListener("click", loadEntity);
languageSelect?.addEventListener("change", () => applyLanguage(languageSelect.value));
controls.indicatorOn.addEventListener("click", () => handleInvocation("light-on"));
controls.indicatorOff.addEventListener("click", () => handleInvocation("light-off"));
controls.temperature.addEventListener("click", () => handleInvocation("temperature"));

setControlsEnabled(false);
applyLanguage(currentLanguage);
