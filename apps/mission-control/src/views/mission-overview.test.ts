import { describe, it, expect } from "vitest";
import { formatUptime } from "./mission-overview";

/**
 * Focused tests for the real-data helpers in the refactored Mission Overview
 * view. These guard the "no fake metrics" directive — uptime must be derived
 * from real gateway uptime_seconds, never a hardcoded "99.2%".
 */
describe("formatUptime (real gateway uptime → display)", () => {
  it("formats seconds only", () => {
    expect(formatUptime(0)).toBe("0s");
    expect(formatUptime(59)).toBe("59s");
  });

  it("formats minutes", () => {
    expect(formatUptime(60)).toBe("1m 0s");
    expect(formatUptime(61)).toBe("1m 1s");
    expect(formatUptime(3599)).toBe("59m 59s");
  });

  it("formats hours", () => {
    expect(formatUptime(3600)).toBe("1h 0m");
    expect(formatUptime(3661)).toBe("1h 1m");
  });

  it("formats days", () => {
    expect(formatUptime(86400)).toBe("1d 0h");
    expect(formatUptime(90000)).toBe("1d 1h");
  });

  it("returns a placeholder for non-finite / negative input", () => {
    expect(formatUptime(Number.NaN)).toBe("—");
    expect(formatUptime(Number.POSITIVE_INFINITY)).toBe("—");
    expect(formatUptime(-5)).toBe("—");
  });
});
