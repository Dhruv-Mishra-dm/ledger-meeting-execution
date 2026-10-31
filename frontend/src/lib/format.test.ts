import { describe, expect, it } from "vitest";
import { errorMessage } from "./api";
import { daysUntil, displayValue, dueLabel, fmtDate } from "./format";

describe("dates", () => {
  it("formats date-only strings without timezone shifts", () => {
    expect(fmtDate("2026-11-08")).toBe("Nov 8, 2026");
    expect(fmtDate("2026-11-08", false)).toBe("Nov 8");
    expect(fmtDate(null)).toBe("—");
  });
  it("computes day differences across month boundaries", () => {
    expect(daysUntil("2026-12-01", "2026-11-30")).toBe(1);
    expect(daysUntil("2026-11-05", "2026-11-07")).toBe(-2);
  });
  it("labels due dates", () => {
    expect(dueLabel("2026-11-05", "2026-11-07")).toEqual({ text: "2d overdue", tone: "danger" });
    expect(dueLabel("2026-11-07", "2026-11-07").text).toBe("Due today");
    expect(dueLabel("2026-11-08", "2026-11-07").text).toBe("Due tomorrow");
    expect(dueLabel(null, "2026-11-07").tone).toBe("muted");
  });
  it("shows decision values by kind", () => {
    expect(displayValue("2026-11-22", "date")).toBe("Nov 22, 2026");
    expect(displayValue("PostgreSQL", "choice")).toBe("PostgreSQL");
  });
});

describe("api errors", () => {
  it("surfaces the server's detail message", () => {
    expect(errorMessage({ detail: "Only approved tasks can be published." }, 409)).toBe("Only approved tasks can be published.");
    expect(errorMessage(null, 0)).toMatch(/backend/);
    expect(errorMessage("oops", 500)).toMatch(/HTTP 500/);
  });
});
