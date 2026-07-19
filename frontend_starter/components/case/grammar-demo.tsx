"use client";

import { useEffect, useState } from "react";
import { reasoningApi } from "@/lib/reasoning-client";
import { SectionLabel } from "./primitives";

const INVALID_EXAMPLE = JSON.stringify(
  { gos_tag: "LOOKS_KINDA_SUSPICIOUS", narration: ["The customer seemed shifty."] },
  null,
  2
);

export function GrammarDemo() {
  const [raw, setRaw] = useState(INVALID_EXAMPLE);
  const [result, setResult] = useState<{ valid: boolean; error: string | null } | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    reasoningApi
      .strSchema()
      .then((s) => setTags(s.gos_tags))
      .catch(() => {});
  }, []);

  async function validate() {
    setBusy(true);
    try {
      setResult(await reasoningApi.validateGrammar(raw));
    } catch (e) {
      setResult({ valid: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <SectionLabel>Constrained decoding — live rejection demo</SectionLabel>
      <div className="rounded-xl border border-border bg-card px-5 py-4">
        <p className="mb-3 text-sm text-muted-foreground">
          The STR is generated under a decoding grammar compiled from a closed JSON schema:
          tokens outside it are <em>masked before sampling</em>, so an invalid ground-of-suspicion
          tag is unreachable — not filtered afterwards. Paste any output below to probe the
          boundary the model physically cannot cross.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              spellCheck={false}
              rows={8}
              className="w-full rounded-lg border border-border bg-background p-3 font-mono text-xs text-muted-foreground outline-none focus:border-foreground/40"
            />
            <button
              onClick={validate}
              disabled={busy}
              className="mt-2 rounded-lg border border-border bg-secondary px-4 py-2 text-sm font-medium transition hover:border-foreground/30 disabled:opacity-50"
            >
              {busy ? "Checking…" : "Check against grammar"}
            </button>
            {result && (
              <div
                className="mt-3 rounded-lg border px-4 py-3 text-sm"
                style={{
                  borderColor: result.valid ? "var(--status-good)" : "var(--status-critical)",
                  color: result.valid ? "var(--status-good)" : "var(--status-critical)",
                }}
              >
                <span aria-hidden="true">{result.valid ? "● " : "▲ "}</span>
                {result.valid
                  ? "Structurally valid — this output is reachable under the grammar."
                  : `REJECTED — ${result.error}`}
              </div>
            )}
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Closed ground-of-suspicion dictionary
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <code
                  key={t}
                  className="rounded border border-border bg-background px-2 py-1 text-[10px] text-muted-foreground"
                >
                  {t}
                </code>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
              During generation these are the <em>only</em> byte sequences the sampler can emit
              for gos_tag. This endpoint replays the same schema checks on pasted text so you can
              see the boundary; in the live pass there is nothing to reject — the invalid tokens
              never get sampled at all.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
