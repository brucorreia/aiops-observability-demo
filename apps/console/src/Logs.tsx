import { useEffect, useMemo, useRef, useState } from "react";
import type { LogLine } from "./types";

function tone(line: LogLine): string {
  const level = (line.level || "").toLowerCase();
  const text = `${line.message} ${line.event || ""}`;
  if (level === "error" || line.status === 500 || /OOMKilled|CrashLoopBackOff|HTTP 500/i.test(text)) {
    return "text-bad";
  }
  if (level === "warn" || level === "warning") return "text-warn";
  return "text-mute";
}

export function Logs({
  demo,
  agent,
}: {
  demo: LogLine[];
  agent: LogLine[];
}) {
  const [tab, setTab] = useState<"demo-app" | "ai-agent">("demo-app");
  const [level, setLevel] = useState("all");
  const [query, setQuery] = useState("");
  const [paused, setPaused] = useState(false);
  const [frozen, setFrozen] = useState<LogLine[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const lines = tab === "demo-app" ? demo : agent;
  const source = paused ? frozen : lines;

  useEffect(() => {
    if (!paused) setFrozen(lines);
  }, [lines, paused]);

  const visible = useMemo(
    () =>
      source.filter((line) => {
        const lvl = (line.level || "info").toLowerCase();
        const matchLevel = level === "all" || lvl === level;
        const hay = `${line.message} ${line.pod || ""}`.toLowerCase();
        return matchLevel && hay.includes(query.toLowerCase());
      }),
    [source, level, query],
  );

  useEffect(() => {
    if (!paused && scroller.current) {
      scroller.current.scrollTop = scroller.current.scrollHeight;
    }
  }, [visible, paused]);

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-line bg-ink">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        {(["demo-app", "ai-agent"] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`rounded px-2 py-1 text-[11px] uppercase tracking-[0.12em] ${
              tab === item ? "bg-raised text-white" : "text-mute"
            }`}
          >
            {item}
          </button>
        ))}
        <select
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          className="rounded border border-line bg-navy px-2 py-1 text-[11px]"
        >
          <option value="all">todos</option>
          <option value="info">INFO</option>
          <option value="warn">WARN</option>
          <option value="error">ERROR</option>
        </select>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="buscar"
          className="w-28 rounded border border-line bg-navy px-2 py-1 text-[11px] outline-none"
        />
        <button
          type="button"
          onClick={() => setPaused((value) => !value)}
          className="ml-auto text-[11px] uppercase tracking-[0.12em] text-mute"
        >
          {paused ? "seguir" : "pausar"}
        </button>
      </div>
      <div ref={scroller} className="min-h-0 flex-1 overflow-auto px-3 py-2 font-mono text-[11px] leading-5">
        {visible.map((line, index) => (
          <div key={`${line.timestamp}-${index}`} className={`grid grid-cols-[96px_120px_1fr] gap-3 ${tone(line)}`}>
            <span>{(line.timestamp || "").slice(11, 19) || "—"}</span>
            <span className="truncate">{line.pod || tab}</span>
            <span className="truncate">
              {(line.level || "info").toUpperCase()} {line.message}
            </span>
          </div>
        ))}
        {!visible.length && <div className="text-mute">sem logs ainda</div>}
      </div>
    </div>
  );
}
