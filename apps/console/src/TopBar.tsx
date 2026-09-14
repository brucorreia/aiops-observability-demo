import { Activity, Maximize2, Pause, Play, ServerCrash, ShieldCheck } from "lucide-react";
import type { ClusterStatus } from "./types";
import { clock } from "./format";

const INCIDENTS = [
  { mode: "crashloop", label: "CrashLoop", icon: ServerCrash },
  { mode: "good", label: "Saudável", icon: ShieldCheck },
] as const;

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] text-mute">
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-ok" : "bg-bad"}`} />
      {label}
    </span>
  );
}

type Props = {
  status: ClusterStatus | null;
  paused: boolean;
  busy?: string | null;
  error?: string | null;
  onTogglePause: () => void;
  onIncident: (mode: string) => void;
};

export function TopBar({ status, paused, busy, error, onTogglePause, onIncident }: Props) {
  const live = status?.connections;
  const auto = Boolean(status?.automatic_execution_allowed);
  return (
    <header className="relative flex h-[72px] items-center gap-6 border-b border-line/80 px-6">
      <div className="flex min-w-[240px] items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-cyan/30 bg-cyan/10">
          <Activity className="h-4 w-4 text-cyan" />
        </div>
        <div>
          <div className="text-[15px] font-medium leading-none">Kube Sentinel</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-mute">AI Operations Center</div>
        </div>
      </div>
      <div className="hidden h-8 w-px bg-line lg:block" />
      <div className="hidden min-w-[180px] lg:block">
        <div className="font-mono text-xs text-cyan">{status?.cluster || "k3d-aiops"}</div>
        <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-mute">
          {status?.environment || "Demo"}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-ok/30 bg-ok/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-ok">
          <span className="h-1.5 w-1.5 rounded-full bg-ok" />
          Live
        </span>
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.16em] ${
            auto ? "border-warn/40 bg-warn/10 text-warn" : "border-line text-mute"
          }`}
        >
          {auto ? "Auto" : "Manual"}
        </span>
        <span className="font-mono text-[11px] text-mute">{clock(status?.updated_at)}</span>
      </div>
      <div className="hidden items-center gap-3 xl:flex">
        <Dot ok={Boolean(live?.kubernetes)} label="Kubernetes" />
        <Dot ok={Boolean(live?.argocd)} label="Argo CD" />
        <Dot ok={Boolean(live?.llm)} label="IA" />
        <Dot ok={Boolean(live?.github)} label="GitHub" />
      </div>
      <div className="ml-auto flex items-center gap-2">
        {INCIDENTS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.mode}
              type="button"
              disabled={Boolean(busy)}
              onClick={() => onIncident(item.mode)}
              className="inline-flex items-center gap-1.5 rounded border border-line bg-raised px-2.5 py-1.5 text-[11px] uppercase tracking-[0.12em] text-mute transition hover:border-cyan/40 hover:text-white disabled:opacity-40"
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={onTogglePause}
          className="rounded border border-line bg-raised p-1.5 text-mute hover:text-white"
          aria-label={paused ? "Retomar" : "Pausar"}
        >
          {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => document.documentElement.requestFullscreen().catch(() => undefined)}
          className="rounded border border-line bg-raised p-1.5 text-mute hover:text-white"
          aria-label="Tela cheia"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>
      {(busy || error) && (
        <div className="absolute left-1/2 top-[72px] z-20 -translate-x-1/2 rounded-b border border-line bg-panel px-3 py-1 text-xs text-warn">
          {error || busy}
        </div>
      )}
    </header>
  );
}
