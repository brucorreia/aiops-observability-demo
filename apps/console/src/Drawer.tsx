import type { Workload } from "./types";
import { relativeTime, statusTone } from "./format";

export function Drawer({
  pod,
  detail,
  insetClass = "right-0",
  onClose,
}: {
  pod: Workload | null;
  detail: Record<string, unknown> | null;
  insetClass?: string;
  onClose: () => void;
}) {
  if (!pod) return null;
  const events = (detail?.events as Array<{ reason?: string; message?: string; type?: string }>) || [];
  const logs = (detail?.logs as string[]) || [];
  const requests = (detail?.requests as Record<string, string>) || {};
  const limits = (detail?.limits as Record<string, string>) || {};
  return (
    <div className={`absolute inset-y-0 z-30 w-[340px] border-l border-line bg-navy/95 p-4 shadow-panel ${insetClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-sm">{pod.name}</div>
          <div className={`mt-1 text-[11px] uppercase tracking-[0.14em] ${statusTone(pod.status)}`}>
            {pod.status}
          </div>
        </div>
        <button type="button" onClick={onClose} className="text-[11px] uppercase tracking-[0.14em] text-mute">
          fechar
        </button>
      </div>
      <dl className="mt-4 space-y-2 text-[12px]">
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Namespace</dt>
          <dd>{pod.namespace}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Node</dt>
          <dd className="truncate">{pod.node || "—"}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Imagem</dt>
          <dd className="max-w-[180px] truncate font-mono">{pod.image || "—"}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Restarts</dt>
          <dd>{pod.restarts}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Idade</dt>
          <dd>{relativeTime(pod.created_at)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Requests</dt>
          <dd className="font-mono">
            {requests.cpu || "—"} / {requests.memory || "—"}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Limits</dt>
          <dd className="font-mono">
            {limits.cpu || "—"} / {limits.memory || "—"}
          </dd>
        </div>
      </dl>
      <h3 className="mt-5 text-[11px] uppercase tracking-[0.16em] text-mute">Eventos</h3>
      <div className="mt-2 max-h-32 space-y-1 overflow-auto text-[11px] text-mute">
        {events.map((item, index) => (
          <div key={index}>
            {item.reason}: {item.message}
          </div>
        ))}
        {!events.length && <div>sem eventos</div>}
      </div>
      <h3 className="mt-4 text-[11px] uppercase tracking-[0.16em] text-mute">Logs recentes</h3>
      <pre className="mt-2 max-h-40 overflow-auto font-mono text-[10px] leading-4 text-mute">
        {logs.join("\n") || "sem logs"}
      </pre>
    </div>
  );
}
