import React from "react";

type Props = {
  onClick: () => void;
  status: "idle" | "submitting" | "generating" | "complete" | "error";
  label?: string;
  disabled?: boolean;
};

const STATUS_LABELS: Record<string, string> = {
  idle: "Generate My Song",
  submitting: "Submitting...",
  generating: "Generating...",
  complete: "Generate Again",
  error: "Try Again",
};

export default function GenerateButton({ onClick, status, label, disabled }: Props) {
  const isLoading = status === "submitting" || status === "generating";
  const isDisabled = isLoading || disabled;

  return (
    <button
      onClick={onClick}
      disabled={isDisabled}
      style={{
        background: isDisabled ? "#333" : "#1db954",
        color: "white",
        border: "none",
        borderRadius: 28,
        padding: "14px 32px",
        fontSize: 16,
        fontWeight: 600,
        cursor: isDisabled ? "not-allowed" : "pointer",
        transition: "all 0.2s",
        opacity: isDisabled ? 0.7 : 1,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {isLoading && (
        <span
          style={{
            display: "inline-block",
            width: 16,
            height: 16,
            border: "2px solid rgba(255,255,255,0.3)",
            borderTopColor: "white",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
            marginRight: 8,
            verticalAlign: "middle",
          }}
        />
      )}
      {label || STATUS_LABELS[status] || "Generate"}
    </button>
  );
}
