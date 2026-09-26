// tests/app.test.js
// Web UI の explicit load / invoke とエラー表示を Vitest で検証する。

import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../public/runtime-loader.js", () => ({
  ARRuntime: vi.fn(),
  InMemorySemanticRegistry: vi.fn((contracts, profiles) => ({ contracts, profiles })),
}));

const page = `
  <select id="language-select"><option value="en">English</option><option value="ja">日本語</option></select>
  <input id="anchor-url" value="/relink/test" />
  <button id="load-button" data-i18n="loadEntity"></button>
  <p id="status"></p>
  <section id="entity-panel" hidden></section>
  <h2 id="entity-title"></h2>
  <span id="capability-list"></span>
  <dd id="profile-claim-status"></dd>
  <dd id="profile-definition-status"></dd>
  <dd id="profile-contract-status"></dd>
  <dd id="profile-conformance-status"></dd>
  <button id="light-on"></button>
  <button id="light-off"></button>
  <button id="temperature-read"></button>
  <pre id="result"></pre>
`;

describe("RELink Web UI", () => {
  let ARRuntime;
  let lightInvoke;
  let temperatureInvoke;
  let InMemorySemanticRegistry;
  let evaluateProfile;

  beforeEach(async () => {
    delete globalThis.RELINK_LAB_CONFIG;
    window.localStorage.clear();
    document.body.innerHTML = page;
    vi.resetModules();
    ({ ARRuntime } = await import("../public/runtime-loader.js"));
    ARRuntime.mockReset();
    ({ InMemorySemanticRegistry } = await import("../public/runtime-loader.js"));
    InMemorySemanticRegistry.mockClear();
    lightInvoke = vi.fn().mockResolvedValue({ values: { state: true } });
    temperatureInvoke = vi.fn().mockResolvedValue({ values: { temperature: 22.4 } });
    evaluateProfile = vi.fn().mockReturnValue({ resolution: "RESOLVED", conformance: "CONFORMANT" });
    const documentModel = {
      url: "https://lab.example/arxml/pico2w.arxml",
      category: "reference-lab.controller",
      profileClaims: [{ href: "https://relink.dev/profiles/reference-lab/controller-monitor/1" }],
      capabilities: [
        {
          localId: "indicator",
          evaluation: { routes: [{ routeId: "indicator-route", availability: "READY" }] },
        },
        {
          localId: "controller-temperature",
          evaluation: { routes: [{ routeId: "temperature-route", availability: "READY" }] },
        },
      ],
      evaluateProfile,
      getCapability: vi.fn((localId) => {
        if (localId === "indicator") {
          return {
            invoke: lightInvoke,
            localId,
            evaluation: { routes: [{ routeId: "indicator-route", availability: "READY" }] },
          };
        }
        if (localId === "controller-temperature") {
          return {
            invoke: temperatureInvoke,
            localId,
            evaluation: { routes: [{ routeId: "temperature-route", availability: "READY" }] },
          };
        }
        return undefined;
      }),
    };
    ARRuntime.mockImplementation(() => ({
      load: vi.fn().mockResolvedValue(documentModel),
    }));
    globalThis.fetch = vi.fn(async (url) => {
      const path = new URL(url).pathname;
      const definitions = {
        "/definitions/contracts/temperature-read.contract.json": {
          identifier: "https://relink.dev/capabilities/temperature/read/1",
        },
        "/definitions/contracts/indicator-set.contract.json": {
          identifier: "https://relink.dev/capabilities/indicator/set/1",
        },
        "/definitions/profiles/controller-monitor.profile.json": {
          identifier: "https://relink.dev/profiles/reference-lab/controller-monitor/1",
          capabilityRequirements: [
            {
              contractIdentifier: "https://relink.dev/capabilities/temperature/read/1",
              required: true,
            },
          ],
        },
      };
      return { ok: Boolean(definitions[path]), json: async () => definitions[path] };
    });
    await import("../public/app.js");
  });

  it("loads capabilities without invoking one automatically", async () => {
    document.querySelector("#load-button").click();
    await vi.waitFor(() => expect(document.querySelector("#status").textContent).toContain("Load succeeded"));

    expect(document.querySelector("#capability-list").textContent).toBe("indicator, controller-temperature");
    expect(document.querySelector("#profile-claim-status").textContent).toBe("present");
    expect(document.querySelector("#profile-definition-status").textContent).toBe("resolved");
    expect(document.querySelector("#profile-contract-status").textContent).toBe("resolved");
    expect(document.querySelector("#profile-conformance-status").textContent).toBe("CONFORMANT");
    expect(lightInvoke).not.toHaveBeenCalled();
    expect(temperatureInvoke).not.toHaveBeenCalled();
    expect(evaluateProfile).toHaveBeenCalledWith(
      "https://relink.dev/profiles/reference-lab/controller-monitor/1",
    );
    expect(InMemorySemanticRegistry).toHaveBeenCalledOnce();
    expect(InMemorySemanticRegistry.mock.calls[0][0]).toHaveLength(2);
    expect(InMemorySemanticRegistry.mock.calls[0][1]).toHaveLength(1);
  });

  it("invokes light only after the user clicks ON", async () => {
    document.querySelector("#load-button").click();
    await vi.waitFor(() => expect(document.querySelector("#light-on").disabled).toBe(false));

    document.querySelector("#light-on").click();
    await vi.waitFor(() => expect(lightInvoke).toHaveBeenCalledOnce());

    expect(lightInvoke).toHaveBeenCalledWith(
      { on: true },
      { accept: "application/json", routeId: "indicator-route" },
    );
    expect(document.querySelector("#result").textContent).toContain('"state": true');
  });

  it("shows a load error instead of leaving a pending UI", async () => {
    ARRuntime.mockImplementation(() => ({ load: vi.fn().mockRejectedValue(new Error("network down")) }));
    document.querySelector("#load-button").click();

    await vi.waitFor(() => expect(document.querySelector("#status").className).toBe("error"));
    expect(document.querySelector("#status").textContent).toContain("network down");
  });

  it("switches fixed and dynamic messages to Japanese", async () => {
    document.querySelector("#language-select").value = "ja";
    document.querySelector("#language-select").dispatchEvent(new Event("change"));

    expect(document.documentElement.lang).toBe("ja");
    document.querySelector("#load-button").click();
    await vi.waitFor(() => expect(document.querySelector("#status").textContent).toContain("ロード成功"));
    expect(document.querySelector("#load-button").textContent).toBe("Entityを読み込む");
  });

  it("uses the Anchor URL supplied by the server configuration", async () => {
    const configuredUrl =
      "https://resolver.relink.test/relink/550e8400-e29b-41d4-a716-446655440000";
    globalThis.RELINK_LAB_CONFIG = { anchorUrl: configuredUrl };
    document.body.innerHTML = page;
    vi.resetModules();

    await import("../public/app.js");

    expect(document.querySelector("#anchor-url").value).toBe(configuredUrl);
  });

  it("keeps the issuer claim separate from a non-conformant evaluation", async () => {
    evaluateProfile.mockReturnValue({ resolution: "RESOLVED", conformance: "NON_CONFORMANT" });
    document.querySelector("#load-button").click();

    await vi.waitFor(() =>
      expect(document.querySelector("#profile-conformance-status").textContent).toBe("NON_CONFORMANT"),
    );
    expect(document.querySelector("#profile-claim-status").textContent).toBe("present");
    expect(document.querySelector("#profile-definition-status").textContent).toBe("resolved");
  });

  it("does not claim conformance when a required Contract definition is unresolved", async () => {
    globalThis.fetch = vi.fn(async (url) => {
      const path = new URL(url).pathname;
      if (path === "/definitions/contracts/temperature-read.contract.json") {
        return { ok: false, json: async () => undefined };
      }
      const definitions = {
        "/definitions/contracts/indicator-set.contract.json": {
          identifier: "https://relink.dev/capabilities/indicator/set/1",
        },
        "/definitions/profiles/controller-monitor.profile.json": {
          identifier: "https://relink.dev/profiles/reference-lab/controller-monitor/1",
          capabilityRequirements: [
            {
              contractIdentifier: "https://relink.dev/capabilities/temperature/read/1",
              required: true,
            },
          ],
        },
      };
      return { ok: Boolean(definitions[path]), json: async () => definitions[path] };
    });
    document.querySelector("#load-button").click();

    await vi.waitFor(() => expect(document.querySelector("#entity-panel").hidden).toBe(false));
    expect(document.querySelector("#profile-definition-status").textContent).toBe("resolved");
    expect(document.querySelector("#profile-contract-status").textContent).toBe("unresolved");
    expect(document.querySelector("#profile-conformance-status").textContent).toBe("UNDETERMINED");
  });

  it("does not enable invocation when multiple READY routes need a choice", async () => {
    ARRuntime.mockImplementation(() => ({
      load: vi.fn().mockResolvedValue({
        url: "https://lab.example/arxml/pico2w.arxml",
        category: "reference-lab.controller",
        profileClaims: [],
        capabilities: [{ localId: "indicator" }, { localId: "controller-temperature" }],
        evaluateProfile: vi.fn().mockReturnValue({ resolution: "UNRESOLVED", conformance: "UNDETERMINED" }),
        getCapability: vi.fn((localId) => ({
          localId,
          evaluation: {
            routes: [
              { routeId: "first", availability: "READY" },
              { routeId: "second", availability: "READY" },
            ],
          },
        })),
      }),
    }));
    document.querySelector("#load-button").click();

    await vi.waitFor(() => expect(document.querySelector("#entity-panel").hidden).toBe(false));
    expect(document.querySelector("#profile-claim-status").textContent).toBe("absent");
    expect(document.querySelector("#profile-definition-status").textContent).toBe("unresolved");
    expect(document.querySelector("#profile-conformance-status").textContent).toBe("UNDETERMINED");
    expect(document.querySelector("#light-on").disabled).toBe(true);
    expect(lightInvoke).not.toHaveBeenCalled();
  });
});
