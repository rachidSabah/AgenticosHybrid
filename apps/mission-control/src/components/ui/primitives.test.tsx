import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Panel, Stat, StatusDot, Badge, Empty } from "./primitives";

describe("UI primitives", () => {
  it("renders a panel with title and subtitle", () => {
    render(<Panel title="Telemetry" subtitle="live"><span>body</span></Panel>);
    expect(screen.getByText("Telemetry")).toBeDefined();
    expect(screen.getByText("live")).toBeDefined();
    expect(screen.getByText("body")).toBeDefined();
  });

  it("renders a stat with value and delta", () => {
    render(<Stat label="Agents" value={7} delta="running" />);
    expect(screen.getByText("Agents")).toBeDefined();
    expect(screen.getByText("7")).toBeDefined();
    expect(screen.getByText("running")).toBeDefined();
  });

  it("renders a status dot without crashing", () => {
    const { container } = render(<StatusDot status="healthy" pulse />);
    expect(container.querySelector("span")).toBeDefined();
  });

  it("renders a badge with tone class", () => {
    render(<Badge tone="ok">ready</Badge>);
    expect(screen.getByText("ready")).toBeDefined();
  });

  it("renders an empty state", () => {
    render(<Empty title="Nothing here" hint="add something" />);
    expect(screen.getByText("Nothing here")).toBeDefined();
    expect(screen.getByText("add something")).toBeDefined();
  });
});
