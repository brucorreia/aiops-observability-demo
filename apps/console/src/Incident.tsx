import { useEffect, useMemo, useState } from "react";
import { ACTION_LABELS, GITOPS_ACTIONS, isGitOpsAction } from "./format";
import type { AnalysisView, EventLine, TimelineStep, Workload } from "./types";

function ScoreBar({
  action,
  label,
  score,
  selected,
  suggested,
  disabled,
  onSelect,
}: {
  action: string;
  label: string;
  score: number;
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
        <div className={`h-full ${selected ? "bg-cyan" : "bg-electric/70"}`} style={{ width: `${score}%` }} />
      </div>
    </button>
  );
}

export function IncidentPanel({
  analysis,
  workload,
  timeline,
  events,
  busy,
  error,
  automaticExecution = false,
  onExecute,
  onClose,
}: {
  analysis: AnalysisView | null;
  workload?: Workload | null;
  timeline: TimelineStep[];
  events: EventLine[];
  busy: boolean;
  error?: string | null;
  automaticExecution?: boolean;
  onExecute: (action: string) => void;
  onClose: () => void;
}) {
  const [evidence, setEvidence] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const ranked = useMemo(() => {
    const scores = new Map(
      (analysis?.recommendations || []).map((item) => [item.action, item.recommendation_score]),
    );
    return GITOPS_ACTIONS.map((action) => ({
      action,
      label: ACTION_LABELS[action],
      score: scores.get(action) ?? 0,
    })).sort((a, b) => b.score - a.score);
  }, [analysis]);
  const suggested = isGitOpsAction(analysis?.recommended_action) ? analysis?.recommended_action : ranked[0]?.action;
  const selected = picked && ranked.some((item) => item.action === picked) ? picked : suggested;
  const selectedLabel = selected ? ACTION_LABELS[selected] : "";

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
        <div className="mt-2 text-[11px] uppercase tracking-[0.14em] text-mute">
          {automaticExecution ? "Execução automática ligada" : "Escolhe a ação GitOps"}
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-4">
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <div className="text-mute">Aplicação</div>
            <div>{analysis?.evidence.deployment || "demo-app"}</div>
          </div>
          <div>
            <div className="text-mute">Deploy</div>
            <div>
              {analysis?.evidence.minutes_since_deployment != null
                ? `${analysis.evidence.minutes_since_deployment} min`
                : "—"}
            </div>
          </div>
          <div>
            <div className="text-mute">SHA</div>
            <div className="font-mono">{analysis?.evidence.git_sha || "—"}</div>
          </div>
          <div>
            <div className="text-mute">Score</div>
            <div>{analysis?.scoring_source || "—"}</div>
          </div>
        </div>
        <div className="space-y-2">
          {ranked.map((item) => (
            <ScoreBar
              key={item.action}
              action={item.action}
              label={item.label}
              score={item.score}
              selected={item.action === selected}
              suggested={item.action === suggested}
              disabled={!analysis?.executable || Boolean(analysis.executed) || busy}
              onSelect={setPicked}
            />
          ))}
          <div className="text-[11px] text-mute">
            A marca IA é a recomendação. Podes executar outra ação mesmo com score mais baixo.
          </div>
        </div>
        <ol className="space-y-2 border-l border-line pl-3">
          {timeline.map((step) => (
            <li key={step.id} className="relative text-[12px]">
              <span
                className={`absolute -left-[19px] top-1 h-2.5 w-2.5 rounded-full ${
                  step.done ? "bg-ok" : step.active ? "bg-cyan" : "bg-line"
                }`}
              />
              <div className={step.active ? "text-white" : "text-mute"}>{step.label}</div>
              {step.detail ? <div className="font-mono text-[10px] text-mute">{step.detail}</div> : null}
            </li>
          ))}
        </ol>
        <div className="space-y-1 font-mono text-[10px] text-mute">
          {events.slice(-8).map((item, index) => (
            <div key={`${item.at}-${index}`}>
              {item.at.slice(11, 19)} {item.event}
            </div>
          ))}
        </div>
        {evidence && analysis?.lecture_text ? (
          <pre className="whitespace-pre-wrap rounded border border-line bg-ink p-3 text-[11px] leading-5 text-mute">
            {analysis.lecture_text}
          </pre>
        ) : null}
      </div>
      <div className="space-y-2 border-t border-line p-4">
        {error ? <div className="text-[11px] text-bad">{error}</div> : null}
        <button
          type="button"
          disabled={!analysis?.executable || analysis.executed || busy || !selected}
          onClick={() => selected && onExecute(selected)}
          className="w-full rounded border border-cyan/40 bg-cyan/15 py-2 text-[12px] uppercase tracking-[0.16em] text-cyan transition hover:bg-cyan/25 disabled:border-line disabled:bg-navy disabled:text-mute"
        >
          {analysis?.executed
            ? "Ação já aplicada"
            : analysis?.executable && selected
              ? `Executar ${selectedLabel}`
              : "Aguardando ação da IA"}
        </button>
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
