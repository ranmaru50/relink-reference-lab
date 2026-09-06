// tests/app.test.js
// Web UI の explicit load / invoke とエラー表示を Vitest で検証する。

import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../public/vendor/relink-web-runtime.js", () => ({
  ARRuntime: vi.fn(),
}));

const page = `
  <input id="anchor-url" value="/relink/test" />
  <button id="load-button"></button>
  <p id="status"></p>
  <section id="entity-panel" hidden></section>
  <h2 id="entity-title"></h2>
  <span id="capability-list"></span>
  <button id="light-on"></button>
  <button id="light-off"></button>
  <button id="temperature-read"></button>
  <pre id="result"></pre>
`;

describe("RELink Web UI", () => {
  let ARRuntime;
  let lightInvoke;
  let temperatureInvoke;

  beforeEach(async () => {
    document.body.innerHTML = page;
    vi.resetModules();
    ({ ARRuntime } = await import("../public/vendor/relink-web-runtime.js"));
    ARRuntime.mockReset();
    lightInvoke = vi.fn().mockResolvedValue({ values: { state: true } });
    temperatureInvoke = vi.fn().mockResolvedValue({ values: { temperature: 22.4 } });
    const documentModel = {
      url: "https://lab.example/arxml/pico2w.arxml",
      category: "environment.lab-device",
      capabilities: [{ localId: "light" }, { localId: "temperature" }],
      getCapability: vi.fn((localId) => {
        if (localId === "light") return { invoke: lightInvoke, localId };
        if (localId === "temperature") return { invoke: temperatureInvoke, localId };
        return undefined;
      }),
    };
    ARRuntime.mockImplementation(() => ({
      load: vi.fn().mockResolvedValue(documentModel),
    }));
    await import("../public/app.js");
  });

  it("loads capabilities without invoking one automatically", async () => {
    document.querySelector("#load-button").click();
    await vi.waitFor(() => expect(document.querySelector("#status").textContent).toContain("ロード成功"));

    expect(document.querySelector("#capability-list").textContent).toBe("light, temperature");
    expect(lightInvoke).not.toHaveBeenCalled();
    expect(temperatureInvoke).not.toHaveBeenCalled();
  });

  it("invokes light only after the user clicks ON", async () => {
    document.querySelector("#load-button").click();
    await vi.waitFor(() => expect(document.querySelector("#light-on").disabled).toBe(false));

    document.querySelector("#light-on").click();
    await vi.waitFor(() => expect(lightInvoke).toHaveBeenCalledOnce());

    expect(lightInvoke).toHaveBeenCalledWith({ on: true }, { accept: "application/json" });
    expect(document.querySelector("#result").textContent).toContain('"state": true');
  });

  it("shows a load error instead of leaving a pending UI", async () => {
    ARRuntime.mockImplementation(() => ({ load: vi.fn().mockRejectedValue(new Error("network down")) }));
    document.querySelector("#load-button").click();

    await vi.waitFor(() => expect(document.querySelector("#status").className).toBe("error"));
    expect(document.querySelector("#status").textContent).toContain("network down");
  });
});
