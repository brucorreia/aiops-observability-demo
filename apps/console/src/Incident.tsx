import { useEffect, useMemo, useState } from "react";
import { ACTION_LABELS, GITOPS_ACTIONS, isGitOpsAction } from "./format";
import type { AnalysisView, Workload } from "./types";

function ScoreBar({
  action,
  label,
  score,
  reasons,
  selected,
  suggested,
  disabled,
  onSelect,
}: {
  action: string;
  label: string;
  score: number;
  reasons: string[];
  selected: boolean;
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
        selected ? "border-cyan/50 bg-cyan/10" : "border-line bg-navy/60 hover:border-cyan/30"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      <div className="flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-2 uppercase tracking-[0.12em] text-mute">
          {label}
          {suggested ? <span className="rounded border border-cyan/40 px-1 text-[9px] text-cyan">IA</span> : null}
        </span>
        <span className={selected ? "text-cyan" : "text-white"}>{score}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-ink">
        <div
          className={`h-full ${selected ? "bg-cyan" : "bg-electric/70"}`}
          style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
        />
      </div>
      {reasons.length ? (
        <ul className="mt-2 space-y-1 text-[11px] leading-4 text-mute">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </button>
  );
}

export function IncidentPanel({
  analysis,
  workload,
  busy,
  onExecute,
  onClose,
}: {
  analysis: AnalysisView | null;
  workload?: Workload | null;
  busy: boolean;
  onExecute: (action: string) => void;
  onClose: () => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const ranked = useMemo(() => {
    if (!analysis?.recommendations?.length) return [];
    const byAction = new Map((analysis.recommendations || []).map((item) => [item.action, item]));
    return GITOPS_ACTIONS.map((action) => {
      const rec = byAction.get(action);
      return {
        action,
        label: rec?.label || ACTION_LABELS[action],
        score: Number(rec?.recommendation_score) || 0,
        reasons: rec?.reasons || [],
      };
    }).sort((a, b) => b.score - a.score);
  }, [analysis]);
  const suggested = isGitOpsAction(analysis?.recommended_action)
    ? analysis.recommended_action
    : ranked[0]?.action;
  const selected = picked && ranked.some((item) => item.action === picked) ? picked : suggested;
  const evidence = analysis?.evidence;
  const commits = evidence?.recent_commits || [];
  const logs = evidence?.log_entries || [];

  useEffect(() => {
    setPicked(null);
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
                reasons={item.reasons}
                selected={item.action === selected}
                suggested={item.action === suggested}
                disabled={!analysis?.executable || Boolean(analysis.executed) || busy}
                onSelect={setPicked}
              />
            ))}
          </div>
        ) : (
          <div className="text-[12px] text-mute">Aguardando o score da IA para este incidente.</div>
        )}
        {analysis ? (
          <div className="space-y-2 rounded border border-line bg-navy/40 p-3">
            <div className="text-[11px] uppercase tracking-[0.14em] text-mute">Evidências</div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <div className="text-mute">SHA</div>
                <div className="font-mono">{evidence?.git_sha || "—"}</div>
              </div>
              <div>
                <div className="text-mute">Deploy</div>
                <div>
                  {evidence?.minutes_since_deployment != null
                    ? `${evidence.minutes_since_deployment} min`
                    : "—"}
                </div>
              </div>
              <div className="col-span-2">
                <div className="text-mute">Término</div>
                <div>{evidence?.last_termination_reason || "—"}</div>
              </div>
            </div>
            {commits.length ? (
              <div className="space-y-1">
                <div className="text-[11px] text-mute">Commits</div>
                {commits.slice(0, 4).map((item) => (
                  <div key={item.sha} className="font-mono text-[10px] text-mute">
                    {item.sha} {item.message}
                  </div>
                ))}
              </div>
            ) : null}
            {logs.length ? (
              <div className="space-y-1">
                <div className="text-[11px] text-mute">Logs</div>
                {logs.slice(0, 5).map((item, index) => (
                  <div key={`${item.event || item.message || "log"}-${index}`} className="text-[10px] text-mute">
                    {item.message || item.event}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="border-t border-line p-4">
        <button
          type="button"
          disabled={!analysis?.executable || analysis.executed || busy || !selected}
          onClick={() => selected && onExecute(selected)}
          className="w-full rounded border border-cyan/40 bg-cyan/15 py-2 text-[12px] uppercase tracking-[0.16em] text-cyan transition hover:bg-cyan/25 disabled:border-line disabled:bg-navy disabled:text-mute"
        >
          {analysis?.executed ? "Ação já aplicada" : "Aplicar"}
        </button>
      </div>
    </aside>
  );
}
