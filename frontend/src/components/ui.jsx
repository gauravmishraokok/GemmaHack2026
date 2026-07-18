export function SectionTitle({ children }) {
  return (
    <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)] mb-3">
      {children}
    </h3>
  );
}

export function Chip({ color, icon, children, title }) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      {icon && <span aria-hidden="true" className="text-[9px]">{icon}</span>}
      {children}
    </span>
  );
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center gap-3 text-[var(--ink-2)]">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--grid)] border-t-[var(--ink-2)]" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function ErrorBox({ error }) {
  return (
    <div
      className="rounded-lg border px-4 py-3 text-sm"
      style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}
    >
      <span aria-hidden="true">▲ </span>
      {String(error)}
    </div>
  );
}

/* Marks AI-generated content, visually separated from raw evidence. */
export function AIBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--cat-company)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--cat-company)]">
      ✦ Gemma-generated
    </span>
  );
}

export function SourceBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--border)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
      ⬒ Raw evidence
    </span>
  );
}
