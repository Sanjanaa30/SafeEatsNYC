import { describe, expect, it } from "vitest";
import {
  correlationDirection,
  correlationLabel,
  correlationStrength,
} from "./correlation";

describe("three-band correlation labels", () => {
  it.each([
    [0, "Weak"],
    [0.29, "Weak"],
    [0.3, "Moderate"],
    [0.59, "Moderate"],
    [0.6, "Strong"],
    [1, "Strong"],
    [-0.65, "Strong"],
  ] as const)("classifies %s as %s", (value, expected) => {
    expect(correlationStrength(value)).toBe(expected);
  });

  it("keeps negative direction separate from strength", () => {
    expect(correlationLabel(-0.45)).toBe("Moderate opposite connection");
    expect(correlationDirection(-0.45)).toBe("Moved in opposite directions");
  });
});
