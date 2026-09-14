import { useState } from "react";
import type { AnalysisView, EventLine, TimelineStep } from "./types";

function ScoreBar({ action, score, active }: { action: string; score: number; active: boolean }) {
  return (
    <div className={`rounded border p-2 ${active ? "border-cyan/50 bg-cyan/10" : "border-line bg-navy/60"}`}>
      <div className="flex items-center justify-between text-[11px]">
        <span className="uppercase tracking-[0.12em] text-mute">{action}</span>
        <span className={active ? "text-cyan" : "text-white"}>{score}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-ink">
        <div className={`h-full ${active ? "bg-cyan" : "bg-electric/70"}`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

export function IncidentPanel({
  analysis,
  timeline,
  events,
  busy,
  error,
  automaticExecution = false,
  onExecute,
}: {
  analysis: AnalysisView | null;
  timeline: TimelineStep[];
  events: EventLine[];
  busy: boolean;
  error?: string | null;
  automaticExecution?: boolean;
  onExecute: () => void;
}) {
  const [evidence, setEvidence] = useState(false);
  const ranked = [...(analysis?.recommendations || [])].sort(
    (a, b) => b.recommendation_score - a.recommendation_score,
  );
  return (
    <aside className="flex min-h-0 w-[380px] shrink-0 flex-col border-l border-line bg-panel/80">
      <div className="border-b border-line px-4 py-3">
        <div className="text-[11px] uppercase tracking-[0.16em] text-mute">AI Incident Analysis</div>
        <div className="mt-1 text-lg">{analysis?.incident_label || "Incidente identificado"}</div>
        <div className="mt-1 text-[12px] text-mute">
          {analysis?.summary || "O Alertmanager disparou após o roll GitOps."}
        </div>
        <div className="mt-2 text-[11px] uppercase tracking-[0.14em] text-mute">
          {automaticExecution ? "Execução automática ligada" : "Decisão manual"}
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
              score={item.recommendation_score}
              active={item.action === analysis?.recommended_action}
            />
          ))}
          {!ranked.length && <div className="text-[12px] text-mute">Sem pontuação ainda.</div>}
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
          disabled={!analysis?.executable || analysis.executed || busy}
          onClick={onExecute}
          className="w-full rounded border border-cyan/40 bg-cyan/15 py-2 text-[12px] uppercase tracking-[0.16em] text-cyan transition hover:bg-cyan/25 disabled:border-line disabled:bg-navy disabled:text-mute"
        >
          {analysis?.executed
            ? "Ação já aplicada"
            : analysis?.executable
              ? `Executar ${analysis.recommended_label}`
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
