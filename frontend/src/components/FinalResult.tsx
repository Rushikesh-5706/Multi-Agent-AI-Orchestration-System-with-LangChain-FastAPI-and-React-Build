import React, { useState } from "react";
import { Check, Copy, AlertOctagon, Sparkles } from "lucide-react";

interface FinalResultProps {
  finalResult: string | null;
  error: string | null;
}

export const FinalResult: React.FC<FinalResultProps> = ({ finalResult, error }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!finalResult) return;
    try {
      await navigator.clipboard.writeText(finalResult);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  if (error) {
    return (
      <section className="final-error-panel" role="alert" aria-label="Workflow failure notification">
        <div className="error-header">
          <AlertOctagon className="error-header-icon" aria-hidden="true" />
          <h3 className="error-title">Workflow Terminated with Error</h3>
        </div>
        <div className="error-body">
          <p className="error-message">{error}</p>
        </div>
      </section>
    );
  }

  if (!finalResult) {
    return null;
  }

  return (
    <section className="final-result-panel" aria-label="Final synthesized result">
      <div className="result-header">
        <div className="result-title-container">
          <Sparkles className="result-header-icon" aria-hidden="true" />
          <h3 className="result-title">Synthesized Final Answer</h3>
        </div>
        <button
          type="button"
          className="copy-button"
          onClick={handleCopy}
          aria-label={copied ? "Copied to clipboard" : "Copy result to clipboard"}
        >
          {copied ? (
            <>
              <Check className="copy-icon" aria-hidden="true" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy className="copy-icon" aria-hidden="true" />
              <span>Copy Answer</span>
            </>
          )}
        </button>
      </div>
      <div className="result-content">
        <p className="result-text">{finalResult}</p>
      </div>
    </section>
  );
};
