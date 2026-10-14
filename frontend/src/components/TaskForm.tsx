import React, { useState } from "react";
import { Send, Loader2 } from "lucide-react";

interface TaskFormProps {
  onSubmit: (prompt: string) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

const EXAMPLE_PROMPTS = [
  "What is the current weather in Tokyo, and based on that, what should I pack?",
  "Find the temperature difference between Tokyo and New York, and calculate the percent change.",
  "Search for the latest developments in quantum computing and summarize the top three breakthroughs.",
];

export const TaskForm: React.FC<TaskFormProps> = ({ onSubmit, isLoading, error }) => {
  const [prompt, setPrompt] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || isLoading) return;
    await onSubmit(trimmed);
  };

  const handleChipClick = (example: string) => {
    setPrompt(example);
  };

  const charCount = prompt.length;
  const isOverLimit = charCount > 2000;
  const isSubmitDisabled = isLoading || charCount === 0 || isOverLimit;

  return (
    <form className="task-form" onSubmit={handleSubmit} aria-label="Task submission form">
      <div className="form-group">
        <label htmlFor="workflow-prompt-input" className="form-label">
          Task Prompt
        </label>
        <textarea
          id="workflow-prompt-input"
          className="form-textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter a multi-step task for the agent team to plan, research, and synthesize..."
          rows={4}
          maxLength={2000}
          disabled={isLoading}
          aria-describedby="char-counter"
        />
        <div className="form-footer">
          <div className="example-chips" role="group" aria-label="Example prompts">
            <span className="chips-label">Examples:</span>
            {EXAMPLE_PROMPTS.map((example, idx) => (
              <button
                key={idx}
                type="button"
                className="chip-button"
                onClick={() => handleChipClick(example)}
                disabled={isLoading}
              >
                {example.length > 40 ? example.slice(0, 40) + "..." : example}
              </button>
            ))}
          </div>
          <span
            id="char-counter"
            className={`char-counter ${isOverLimit ? "char-counter-error" : ""}`}
            aria-live="polite"
          >
            {charCount} / 2000
          </span>
        </div>
      </div>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <div className="form-actions">
        <button
          type="submit"
          className="submit-button"
          disabled={isSubmitDisabled}
          id="start-workflow-button"
        >
          {isLoading ? (
            <>
              <Loader2 className="button-icon spin-icon" aria-hidden="true" />
              <span>Starting...</span>
            </>
          ) : (
            <>
              <Send className="button-icon" aria-hidden="true" />
              <span>Start Workflow</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
};
