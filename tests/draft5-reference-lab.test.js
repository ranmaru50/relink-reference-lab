// tests/draft5-reference-lab.test.js
// Runtime 0.2.0 で Draft 5 fixture と semantic Profile を実環境と同じ API で検証する。

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { ARRuntime, InMemorySemanticRegistry } from "../public/vendor/relink-web-runtime.js";

const readFixture = (path) => readFile(fileURLToPath(new URL(path, import.meta.url)), "utf8");

async function loadDefinitions() {
  const [temperatureContract, indicatorContract, controllerProfile] = await Promise.all([
    readFixture("../public/definitions/contracts/temperature-read.contract.json"),
    readFixture("../public/definitions/contracts/indicator-set.contract.json"),
    readFixture("../public/definitions/profiles/controller-monitor.profile.json"),
  ]);
  return new InMemorySemanticRegistry(
    [JSON.parse(temperatureContract), JSON.parse(indicatorContract)],
    [JSON.parse(controllerProfile)],
  );
}

describe("Reference Lab Draft 5 semantic flow", () => {
  it("resolves exact definitions, evaluates Profile, and invokes only on explicit request", async () => {
    const [xml, semanticRegistry] = await Promise.all([
      readFixture("../public/arxml/pico2w.arxml"),
      loadDefinitions(),
    ]);
    const invoke = vi.fn(async (url, request) => ({
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () => url.pathname === "/api/temperature"
        ? JSON.stringify({ temperature: 22.4 })
        : JSON.stringify({ state: true }),
      blob: async () => new Blob(),
      request,
    }));
    const runtime = new ARRuntime({
      resourceFetcher: { fetchText: vi.fn().mockResolvedValue(xml) },
      httpInvoker: { invoke },
      semanticRegistry,
    });

    // documentFormat を指定せず、Runtime 既定の Draft 5 として parse する。
    const document = await runtime.load("https://lab.example/arxml/pico2w.arxml");
    expect(document.profileClaims).toMatchObject([
      { href: "https://relink.dev/profiles/reference-lab/controller-monitor/1" },
    ]);
    expect(document.evaluateProfile("https://relink.dev/profiles/reference-lab/controller-monitor/1"))
      .toEqual({ resolution: "RESOLVED", conformance: "CONFORMANT" });
    expect(document.evaluateCapability("controller-temperature")).toMatchObject({
      contractResolution: "RESOLVED",
      projectionValidation: "VALIDATED",
      availability: "READY",
      routes: [{ availability: "READY" }],
    });
    expect(document.evaluateCapability("indicator")).toMatchObject({
      contractResolution: "RESOLVED",
      projectionValidation: "VALIDATED",
      availability: "READY",
    });
    expect(invoke).not.toHaveBeenCalled();

    const temperature = document.getCapability("controller-temperature");
    const routeId = temperature.evaluation.routes[0].routeId;
    const temperatureResult = await temperature.invoke({}, { routeId });
    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke.mock.calls[0][0].href).toBe("https://lab.example/api/temperature");
    expect(temperatureResult.values).toEqual({ temperature: 22.4 });

    const indicator = document.getCapability("indicator");
    const indicatorRouteId = indicator.evaluation.routes[0].routeId;
    const indicatorResult = await indicator.invoke({ on: true }, { routeId: indicatorRouteId });
    expect(invoke).toHaveBeenCalledTimes(2);
    expect(indicatorResult.values).toEqual({ state: true });
  });

  it.each([
    { capabilityId: "controller-temperature", inputs: {}, scalar: 22.4 },
    { capabilityId: "indicator", inputs: { on: true }, scalar: true },
  ])("rejects a Draft 5 single-Output scalar response for $capabilityId", async ({
    capabilityId,
    inputs,
    scalar,
  }) => {
    const [xml, semanticRegistry] = await Promise.all([
      readFixture("../public/arxml/pico2w.arxml"),
      loadDefinitions(),
    ]);
    const runtime = new ARRuntime({
      resourceFetcher: { fetchText: vi.fn().mockResolvedValue(xml) },
      httpInvoker: {
        invoke: vi.fn(async () => ({
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          text: async () => JSON.stringify(scalar),
          blob: async () => new Blob(),
        })),
      },
      semanticRegistry,
    });
    const document = await runtime.load("https://lab.example/arxml/pico2w.arxml");
    const capability = document.getCapability(capabilityId);
    const routeId = capability.evaluation.routes[0].routeId;

    await expect(capability.invoke(inputs, { routeId }))
      .rejects.toThrow("JSON Result は top-level object である必要があります");
  });

  it("evaluates the same Profile for a different local ID and HTTP path", async () => {
    const [xml, semanticRegistry] = await Promise.all([
      readFixture("../public/arxml/simulator-controller.arxml"),
      loadDefinitions(),
    ]);
    const runtime = new ARRuntime({
      resourceFetcher: { fetchText: vi.fn().mockResolvedValue(xml) },
      semanticRegistry,
    });
    const document = await runtime.load("https://simulator.example/arxml/controller.arxml");

    expect(document.capabilities.map((capability) => capability.localId)).toEqual([
      "controller-thermal-reading",
    ]);
    expect(document.evaluateProfile("https://relink.dev/profiles/reference-lab/controller-monitor/1"))
      .toEqual({ resolution: "RESOLVED", conformance: "CONFORMANT" });
    expect(document.getCapability("controller-thermal-reading").evaluation.routes)
      .toHaveLength(1);
  });

  it("keeps unresolved definitions undetermined and reports a false claim as non-conformant", async () => {
    const xml = (await readFixture("../public/arxml/pico2w.arxml"))
      .replace('type="https://relink.dev/capabilities/temperature/read/1"',
        'type="https://relink.dev/capabilities/temperature/read/2"');
    const document = await new ARRuntime({
      resourceFetcher: { fetchText: vi.fn().mockResolvedValue(xml) },
      semanticRegistry: new InMemorySemanticRegistry([], []),
    }).load("https://lab.example/arxml/pico2w.arxml");

    expect(document.profileClaims).toHaveLength(1);
    expect(document.evaluateProfile("https://relink.dev/profiles/reference-lab/controller-monitor/1"))
      .toEqual({ resolution: "UNRESOLVED", conformance: "UNDETERMINED" });
  });

  it("reports a resolved Profile claim as non-conformant when its required Capability is absent", async () => {
    const xml = (await readFixture("../public/arxml/pico2w.arxml"))
      .replace(/\s*<capability\s+id="controller-temperature"[\s\S]*?<\/capability>/, "");
    const document = await new ARRuntime({
      resourceFetcher: { fetchText: vi.fn().mockResolvedValue(xml) },
      semanticRegistry: await loadDefinitions(),
    }).load("https://lab.example/arxml/pico2w.arxml");

    expect(document.profileClaims).toHaveLength(1);
    expect(document.evaluateProfile("https://relink.dev/profiles/reference-lab/controller-monitor/1"))
      .toEqual({ resolution: "RESOLVED", conformance: "NON_CONFORMANT" });
  });
});
