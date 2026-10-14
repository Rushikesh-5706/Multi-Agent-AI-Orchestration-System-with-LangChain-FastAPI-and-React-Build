import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TaskForm } from "./TaskForm";

describe("TaskForm", () => {
  it("renders with empty textarea and disabled submit button", () => {
    render(<TaskForm onSubmit={vi.fn()} isLoading={false} error={null} />);
    const textarea = screen.getByLabelText(/task prompt/i);
    expect(textarea).toBeInTheDocument();
    const button = screen.getByRole("button", { name: /start workflow/i });
    expect(button).toBeDisabled();
    expect(screen.getByText("0 / 2000")).toBeInTheDocument();
  });

  it("enables submit button when valid text is typed and calls onSubmit", () => {
    const handleSubmit = vi.fn();
    render(<TaskForm onSubmit={handleSubmit} isLoading={false} error={null} />);
    const textarea = screen.getByLabelText(/task prompt/i);
    fireEvent.change(textarea, { target: { value: "Investigate weather in Tokyo" } });

    const button = screen.getByRole("button", { name: /start workflow/i });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(handleSubmit).toHaveBeenCalledWith("Investigate weather in Tokyo");
  });

  it("fills textarea when an example chip is clicked", () => {
    render(<TaskForm onSubmit={vi.fn()} isLoading={false} error={null} />);
    const chip = screen.getAllByRole("button")[0];
    fireEvent.click(chip);
    const textarea = screen.getByLabelText(/task prompt/i) as HTMLTextAreaElement;
    expect(textarea.value.length).toBeGreaterThan(0);
  });

  it("displays inline error when passed", () => {
    render(<TaskForm onSubmit={vi.fn()} isLoading={false} error="Validation failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Validation failed");
  });
});
