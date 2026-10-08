import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no layout observer. Chart dimensions are synthetic test geometry only.
globalThis.ResizeObserver = class implements ResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}
  observe(target: Element) { this.callback([{target, contentRect: new DOMRect(0, 0, 640, 270)} as ResizeObserverEntry], this); }
  unobserve() {}
  disconnect() {}
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
Object.defineProperty(window, "scrollTo", {value: vi.fn(), writable: true});
