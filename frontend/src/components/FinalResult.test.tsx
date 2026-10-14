import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FinalResult } from "./FinalResult";

describe("FinalResult", () => {
  it("renders nothing when neither result nor error exists", () => {
    const { container } = render(<FinalResult finalResult={null} error={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders error panel on fatal error", () => {
    render(<FinalResult finalResult={null} error="Critical failure in agent workflow" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Critical failure in agent workflow")).toBeInTheDocument();
  });

  it("renders final result with copy button", () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });

    render(<FinalResult finalResult="Tokyo is 18C, pack a windbreaker." error={null} />);
    expect(screen.getByText("Synthesized Final Answer")).toBeInTheDocument();
    expect(screen.getByText("Tokyo is 18C, pack a windbreaker.")).toBeInTheDocument();

    const copyBtn = screen.getByRole("button", { name: /copy result/i });
    expect(copyBtn).toBeInTheDocument();
    act(() => {
      fireEvent.click(copyBtn);
    });
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("Tokyo is 18C, pack a windbreaker.");
  });
});
