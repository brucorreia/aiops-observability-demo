export function formatBytes(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  const units = ["B", "KiB", "MiB", "GiB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatCores(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(0)}m`;
}

export function relativeTime(value?: string | null): string {
  if (!value) return "—";
  const then = Date.parse(value);
  if (Number.isNaN(then)) return value;
  const delta = Math.max(0, Date.now() - then);
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  return `${Math.floor(hours / 24)} d`;
}

export function clock(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function statusTone(status: string): string {
  if (status === "Running" || status === "Healthy") return "text-ok";
  if (status === "Pending") return "text-warn";
  return "text-bad";
}
