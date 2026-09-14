export type ConnectionMap = {
  kubernetes: boolean;
  argocd: boolean;
  llm: boolean;
  github: boolean;
};

export type Workload = {
  name: string;
  namespace: string;
  node?: string;
  app?: string;
  phase: string;
  ready: boolean;
  status: string;
  reason?: string;
  restarts: number;
  image?: string;
  container?: string;
  created_at?: string;
};

export type TimelineStep = {
  id: string;
  label: string;
  detail?: string | null;
  done: boolean;
  active?: boolean;
};

export type Recommendation = {
  action: string;
  recommendation_score: number;
  reasons?: string[];
};

export type AnalysisView = {
  id: string;
  incident_type: string;
  incident_label: string;
  summary: string;
  lecture_text: string;
  recommended_action: string;
  recommended_label: string;
  scoring_source: string;
  automatic_execution_allowed: boolean;
  executable: boolean;
  executed: boolean;
  approvals: Array<{ decision: string; executed: boolean; detail: string; at: string }>;
  recommendations: Recommendation[];
  evidence: {
    deployment?: string;
    namespace?: string;
    git_sha?: string;
    current_image?: string;
    minutes_since_deployment?: number;
    recent_deployment?: boolean;
    restarts?: number;
    last_termination_reason?: string;
    recent_commits: Array<{ sha: string; message: string }>;
    log_entries: Array<{ message?: string; event?: string; status?: number }>;
  };
};

export type ClusterStatus = {
  cluster: string;
  environment: string;
  updated_at: string;
  health: "Healthy" | "Degraded" | string;
  error?: string | null;
  connections: ConnectionMap;
  nodes: { ready: number; total: number; items: Array<{ name: string; ready: boolean }> };
  pods: { running: number; total: number };
  cpu: { cores: number | null; sparkline: number[] };
  memory: { bytes: number | null; sparkline: number[] };
  restarts: number;
  demo_app: {
    ready: number;
    total: number;
    image?: string;
    git_sha?: string;
    deployed_at?: string;
    mode?: string;
    health?: { status?: string } | null;
    api?: { status?: number; version?: string } | null;
  };
  workloads: Workload[];
  topology: {
    nodes: Array<{ name: string; ready: boolean; pods: Workload[] }>;
    unscheduled: Workload[];
  };
  rollout: {
    mode?: string;
    sha?: string;
    short_sha?: string;
    message?: string;
    image_synced?: boolean;
    workflow?: { status?: string; conclusion?: string };
  };
  analysis: Record<string, unknown> | null;
  timeline: TimelineStep[];
};

export type LogLine = {
  timestamp?: string;
  level?: string;
  pod?: string;
  message: string;
  status?: number;
  event?: string;
};

export type EventLine = {
  at: string;
  event: string;
  [key: string]: unknown;
};
