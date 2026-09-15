import { useEffect, useMemo, useState } from "react";
import { ACTION_LABELS, GITOPS_ACTIONS, isGitOpsAction } from "./format";
import type { AnalysisView, Workload } from "./types";

function ScoreBar({
  action,
  label,
  score,
  suggested,
  disabled,
  onSelect,
}: {
  action: string;
  label: string;
  score: number;
  suggested: boolean;
  disabled: boolean;
  onSelect: (action: string) => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect(action)}
      className={`w-full rounded border p-2 text-left transition ${
        suggested ? "border-cyan/50 bg-cyan/10" : "border-line bg-navy/60 hover:border-cyan/30"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      <div className="flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-2 uppercase tracking-[0.12em] text-mute">
          {label}
          {suggested ? <span className="rounded border border-cyan/40 px-1 text-[9px] text-cyan">IA</span> : null}
        </span>
        <span className={suggested ? "text-cyan" : "text-white"}>{score}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-ink">
        <div className={`h-full ${suggested ? "bg-cyan" : "bg-electric/70"}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
    </button>
  );
}

export function IncidentPanel({
  analysis,
  workload,
  busy,
  error,
  onExecute,
  onClose,
}: {
  analysis: AnalysisView | null;
  workload?: Workload | null;
  busy: boolean;
  error?: string | null;
  onExecute: (action: string) => void;
  onClose: () => void;
}) {
  const [evidence, setEvidence] = useState(false);
  const ranked = useMemo(() => {
    const scores = new Map(
      (analysis?.recommendations || []).map((item) => [item.action, Number(item.recommendation_score) || 0]),
    );
    if (!analysis?.recommendations?.length) return [];
    return GITOPS_ACTIONS.map((action) => ({
      action,
      label: ACTION_LABELS[action],
      score: scores.get(action) ?? 0,
    })).sort((a, b) => b.score - a.score);
  }, [analysis]);
  const suggested = isGitOpsAction(analysis?.recommended_action)
    ? analysis.recommended_action
    : ranked[0]?.action;

  useEffect(() => {
    setEvidence(false);
  }, [analysis?.id]);

  return (
    <aside className="flex min-h-0 w-[380px] shrink-0 flex-col border-l border-line bg-panel/80">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-mute">AI Incident Analysis</div>
            <div className="mt-1 text-lg">{analysis?.incident_label || workload?.status || "Incidente"}</div>
          </div>
          <button type="button" onClick={onClose} className="text-[11px] uppercase tracking-[0.14em] text-mute">
            fechar
          </button>
        </div>
        <div className="mt-1 text-[12px] text-mute">
          {analysis?.summary ||
            `Selecionado: ${workload?.app || workload?.name}. Aguardando o score do alerta.`}
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-4">
        {ranked.length ? (
          <div className="space-y-2">
            {ranked.map((item) => (
              <ScoreBar
                key={item.action}
                action={item.action}
                label={item.label}
                score={item.score}
                suggested={item.action === suggested}
                disabled={!analysis?.executable || Boolean(analysis.executed) || busy}
                onSelect={onExecute}
              />
            ))}
            <div className="text-[11px] text-mute">Clica numa ação para a executar via GitOps.</div>
          </div>
        ) : (
          <div className="text-[12px] text-mute">Aguardando o score da IA para este incidente.</div>
        )}
        {error ? <div className="text-[11px] text-bad">{error}</div> : null}
        {evidence && analysis?.lecture_text ? (
          <pre className="whitespace-pre-wrap rounded border border-line bg-ink p-3 text-[11px] leading-5 text-mute">
            {analysis.lecture_text}
          </pre>
        ) : null}
      </div>
      <div className="border-t border-line p-4">
        <button
          type="button"
          disabled={!analysis}
          onClick={() => setEvidence((value) => !value)}
          className="w-full rounded border border-line py-2 text-[11px] uppercase tracking-[0.14em] text-mute hover:text-white disabled:opacity-40"
        >
          {evidence ? "Ocultar evidências" : "Ver evidências"}
        </button>
      </div>
    </aside>
  );
}
