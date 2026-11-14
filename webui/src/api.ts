export type Params = Record<string, number | string | boolean>;

export type Draft = {
  arch: string;
  model_name: string;
  output_target: string;
  primary_stem?: string;
  params: Params;
  summary?: string;
  start_sec: number;
  end_sec: number;
};

export type Artifact = {
  id: string;
  role: string;
  label: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  format: string;
};

export type Job = {
  id: string;
  task_id: string;
  variant_id: string;
  kind: string;
  status: string;
  stage: string;
  progress: number | null;
  error: string;
  note: string;
  hold: boolean;
  start_sec: number | null;
  end_sec: number | null;
  model_name: string;
  summary: string;
  spec: Draft;
  artifacts: Artifact[];
  created_at: string;
  updated_at: string;
};

export type Variant = {
  id: string;
  label: string;
  spec: Draft;
  reason: string;
  jobs: Job[];
  created_at: string;
};

export type TaskStatus = {
  state: string;
  progress: number | null;
  stage: string;
  error: string;
  note: string;
  kind: string;
  job_id: string;
};

export type Task = {
  id: string;
  title: string;
  filename: string;
  duration_sec: number | null;
  sample_rate: number | null;
  channels: number | null;
  goal: string;
  draft: Draft;
  selected_variant_id: string | null;
  created_at: string;
  status: TaskStatus;
  variants: Variant[];
};

export type TaskSummary = {
  id: string;
  title: string;
  filename: string;
  duration_sec: number | null;
  goal: string;
  created_at: string;
  selected_variant_id: string | null;
  status: TaskStatus;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  refs: { type: string; id: string; variant_id?: string; task_id?: string }[];
  created_at: string;
};

export type Hardware = {
  sampled_at: string | null;
  cpu_percent: number | null;
  memory_used: number | null;
  memory_total: number | null;
  gpu: {
    available: boolean;
    name: string | null;
    utilization: number | null;
    memory_used: number | null;
    memory_total: number | null;
  };
  error: string;
};

export type Health = {
  ok: boolean;
  llm_configured: boolean;
  device: string;
  inference_python: string[];
  inference_blocked: boolean;
  torch: string | null;
  data_dir: string;
};

export type ModelRow = {
  name: string;
  display_name: string;
  arch: string;
  installed: boolean;
  executable: boolean;
  files: string[];
  outputs?: string[];
};

export type DownloadRow = {
  id: string;
  model_name: string;
  arch: string;
  status: string;
  progress: number | null;
  stage: string;
  error: string;
};

export type Preset = {
  id: string;
  arch: string;
  model_name: string;
  output_target: string;
  primary_stem?: string;
  params: Params;
  summary: string;
  use: string;
  when: string;
};

export type Meta = {
  presets: Preset[];
  targets: Record<string, string[]>;
  wav_types: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = "请求失败";
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  hardware: () => request<Hardware>("/api/hardware"),
  meta: () => request<Meta>("/api/meta"),
  tasks: (scope: string) => request<{ tasks: TaskSummary[] }>(`/api/tasks?scope=${scope}`),
  task: (id: string) => request<Task>(`/api/tasks/${id}`),
  messages: (id: string) => request<{ messages: ChatMessage[] }>(`/api/tasks/${id}/messages`),
  models: () => request<{ models: ModelRow[]; warning: string }>("/api/models"),
  downloads: () => request<{ downloads: DownloadRow[] }>("/api/downloads"),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Task>("/api/tasks", { method: "POST", body });
  },
  saveDraft: (id: string, draft: Draft) =>
    request<Task>(`/api/tasks/${id}/draft`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft }),
    }),
  preview: (id: string, draft: Draft, requestKey: string) =>
    request<Job>(`/api/tasks/${id}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft, request_key: requestKey, reason: "手动提交试听" }),
    }),
  select: (id: string, variantId: string) =>
    request<Task>(`/api/tasks/${id}/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variant_id: variantId }),
    }),
  run: (id: string, variantId: string | null, targets: string[] | null, requestKey: string) =>
    request<{ jobs: Job[] }>(`/api/tasks/${id}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variant_id: variantId,
        target_task_ids: targets,
        request_key: requestKey,
        reason: targets && targets.length > 1 ? "手动批量处理" : "手动处理整首",
      }),
    }),
  speak: (id: string, text: string, targets: string[]) =>
    request<{ task: Task; messages: ChatMessage[] }>(`/api/tasks/${id}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, target_task_ids: targets }),
    }),
  cancel: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
  continueJob: (id: string) => request<Job>(`/api/jobs/${id}/continue`, { method: "POST" }),
  downloadModel: (arch: string, modelName: string) =>
    request<DownloadRow>("/api/models/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arch, model_name: modelName, request_key: requestKey() }),
    }),
};

export function requestKey(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function clock(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "--:--";
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  const remain = whole % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remain).padStart(2, "0")}`;
}

export function gigabytes(bytes: number | null): string {
  if (bytes == null) return "不可用";
  return (bytes / 1024 ** 3).toFixed(1);
}

export const STATE_LABEL: Record<string, string> = {
  empty: "等待处理",
  queued: "排队中",
  running: "处理中",
  waiting_model: "等待模型",
  paused: "排队已暂停",
  blocked: "等待上次进程退出",
  succeeded: "已完成",
  failed: "处理失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

export const STAGE_LABEL: Record<string, string> = {
  preparing: "准备音频",
  download: "下载模型",
  load: "加载模型",
  inference: "分离中",
  save: "保存结果",
  running: "处理中",
  cancelling: "正在取消",
  complete: "完成",
  waiting_model: "等待模型",
  paused: "排队已暂停",
  blocked: "推理进程仍在退出",
  size_unknown: "下载中，大小未知",
  queued: "排队中",
};

export const TARGET_LABEL: Record<string, string> = {
  instrumental: "伴奏",
  vocals: "人声",
  drums: "鼓",
  bass: "贝斯",
  other: "其他",
  guitar: "吉他",
  piano: "钢琴",
  no_drums: "无鼓",
  no_bass: "无贝斯",
  no_other: "无其他",
  no_guitar: "无吉他",
  no_piano: "无钢琴",
  Kick: "底鼓",
  Snare: "军鼓",
  Toms: "通通鼓",
  Hh: "踩镲",
  Ride: "叮叮镲",
  Crash: "吊镲",
  "No Reverb": "无混响",
  "No Drum-Bass": "无鼓和贝斯",
  Similarity: "相似度",
  all: "全部音轨",
};

export function outputMenu(arch: string, modelName: string, outputs?: string[]): string[] {
  if (outputs && outputs.length) return outputs;
  const folded = modelName.toLowerCase();
  if (arch === "demucs") {
    if (modelName.includes("UVR_Model") || folded.includes("uvr model") || folded.includes("2stem")) return ["vocals", "instrumental", "all"];
    if (folded.includes("htdemucs_6s") || folded.includes("6s")) return ["all", "vocals", "other", "bass", "drums", "guitar", "piano"];
    return ["all", "vocals", "other", "bass", "drums"];
  }
  if (folded.includes("4-stem") || folded.includes("4_stem") || folded.includes("4 stem") || folded.includes("4stem")) {
    return ["all", "vocals", "drums", "bass", "other"];
  }
  const primary = folded.includes("inst") || folded.includes("karaoke") ? "instrumental"
    : folded.includes("drum") ? "drums"
    : folded.includes("bass") ? "bass"
    : "vocals";
  const pair: Record<string, string> = {
    vocals: "instrumental",
    instrumental: "vocals",
    drums: "no_drums",
    bass: "no_bass",
  };
  return [primary, pair[primary] || "instrumental", "all"];
}

export function statusLine(status: TaskStatus): string {
  if (status.state === "succeeded" && status.kind === "preview") return "试听就绪";
  if (status.state === "succeeded" && status.kind === "full") return "整首完成";
  if (status.state === "running" && status.progress != null) return `处理中 · ${Math.round(status.progress)}%`;
  if (status.note) return status.note;
  return STATE_LABEL[status.state] || status.state;
}
