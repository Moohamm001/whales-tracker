import React from "react";

const PHASE_STYLE: Record<string, string> = {
  "undiscovered":        "bg-muted/10 text-muted border-muted/30",
  "early-accumulation":  "bg-good/15  text-good  border-good/40",
  "consensus-build":     "bg-info/15  text-info  border-info/40",
  "crowded":             "bg-warn/15  text-warn  border-warn/40",
  "topping":             "bg-warn/15  text-warn  border-warn/40",
  "distribution":        "bg-bad/15   text-bad   border-bad/40",
  "holding":             "bg-muted/10 text-muted border-muted/30",
  "building":            "bg-info/15  text-info  border-info/40",
  "trimming":            "bg-warn/15  text-warn  border-warn/40",
  "exited":              "bg-bad/15   text-bad   border-bad/30",
};

const PHASE_LABEL: Record<string, string> = {
  "undiscovered":        "Undiscovered",
  "early-accumulation":  "Early accumulation",
  "consensus-build":     "Consensus building",
  "crowded":             "Crowded",
  "topping":             "Topping",
  "distribution":        "Distribution",
  "holding":             "Holding",
  "building":            "Building",
  "trimming":            "Trimming",
  "exited":              "Exited",
};

export default function PhaseBadge({ phase }: { phase: string | null | undefined }) {
  if (!phase) return null;
  const cls = PHASE_STYLE[phase] ?? PHASE_STYLE["holding"];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${cls}`}>
      {PHASE_LABEL[phase] ?? phase}
    </span>
  );
}

const PATTERN_STYLE: Record<string, string> = {
  "probe":              "bg-info/10  text-info  border-info/30",
  "pyramid":            "bg-good/10  text-good  border-good/30",
  "linear-accumulate":  "bg-good/15  text-good  border-good/40",
  "re-entry":           "bg-info/10  text-info  border-info/30",
  "single-shot":        "bg-muted/10 text-muted border-muted/30",
  "distribute":         "bg-bad/10   text-bad   border-bad/30",
  "stable":             "bg-muted/10 text-muted border-muted/30",
};

const PATTERN_LABEL: Record<string, string> = {
  "probe":              "Probe",
  "pyramid":            "Pyramid",
  "linear-accumulate":  "Linear accum.",
  "re-entry":           "Re-entry",
  "single-shot":        "Single-shot",
  "distribute":         "Distribute",
  "stable":             "Stable",
};

export function PatternBadge({ pattern }: { pattern: string | null | undefined }) {
  if (!pattern) return <span className="text-muted text-xs">—</span>;
  const cls = PATTERN_STYLE[pattern] ?? PATTERN_STYLE["stable"];
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${cls}`}>
      {PATTERN_LABEL[pattern] ?? pattern}
    </span>
  );
}

export function ConvictionStars({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-muted text-xs">—</span>;
  // 0–100 → 0–5 stars
  const n = Math.max(0, Math.min(5, Math.round(score / 20)));
  return (
    <span className="text-warn tabular-nums" title={`Conviction score: ${score}/100`}>
      {"★".repeat(n)}<span className="text-muted">{"☆".repeat(5 - n)}</span>
    </span>
  );
}
