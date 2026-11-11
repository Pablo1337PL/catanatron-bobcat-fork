import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { loadShowLabels, saveShowLabels } from "./preferences";

/** The test environment has no working localStorage: an in-memory one. */
function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => [...items.keys()][index] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, String(value)),
  };
}

describe("tile letters preference", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("on by default, remembered when turned off", () => {
    expect(loadShowLabels()).toBe(true);
    saveShowLabels(false);
    expect(loadShowLabels()).toBe(false);
    saveShowLabels(true);
    expect(loadShowLabels()).toBe(true);
  });

  test("blocked storage breaks nothing", () => {
    const blocked = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    vi.stubGlobal("localStorage", blocked);
    expect(() => saveShowLabels(false)).not.toThrow();
    expect(loadShowLabels()).toBe(true);
  });
});
