import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
      {children}
    </h3>
  );
}

export function Chip({
  color,
  icon,
  children,
  title,
}: {
  color: string;
  icon?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      {icon && (
        <span aria-hidden="true" className="text-[9px]">
          {icon}
        </span>
      )}
      {children}
    </span>
  );
}

export function InlineSpinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  return (
    <div
      className="rounded-lg border px-4 py-3 text-sm"
      style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}
    >
      <span aria-hidden="true">▲ </span>
      {String(error instanceof Error ? error.message : error)}
    </div>
  );
}

/** Marks AI-generated content, visually separated from raw evidence. */
export function AIBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--cat-company)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--cat-company)]">
      ✦ Gemma-generated
    </span>
  );
}

export function SourceBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
      ⬒ Raw evidence
    </span>
  );
}

export function CasePanel({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`rounded-xl border border-border bg-card px-5 py-4 ${className}`}>{children}</div>
  );
}
