import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  clock,
  gigabytes,
  requestKey,
  statusLine,
  outputMenu,
  TARGET_LABEL,
  type ChatMessage,
  type Draft,
  type Hardware,
  type Health,
  type Job,
  type Meta,
  type ModelRow,
  type DownloadRow,
  type Task,
  type TaskSummary,
  type Variant,
} from "./api";
import { Markdown } from "./markdown";
import { Models } from "./Models";
import { Player, type LaneModel } from "./Player";

type View = "work" | "models";

export function App() {
  const [view, setView] = useState<View>("work");
  const [scope, setScope] = useState("all");
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftOwner, setDraftOwner] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hardware, setHardware] = useState<Hardware | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [models, setModels] = useState<ModelRow[]>([]);
  const [downloads, setDownloads] = useState<DownloadRow[]>([]);
  const [modelWarning, setModelWarning] = useState("");
  const [checked, setChecked] = useState<string[]>([]);
  const [laneId, setLaneId] = useState("source");
  const [laneToken, setLaneToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const messagePane = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const schemeRef = useRef<HTMLElement>(null);
  const previewKey = useRef(requestKey());
  const runKey = useRef(requestKey());

  useEffect(() => {
    void api.health().then(setHealth).catch((reason: Error) => setError(reason.message));
    void api.meta().then(setMeta).catch((reason: Error) => setError(reason.message));
    void api.hardware().then(setHardware).catch(() => undefined);
    void api.models().then((body) => setModels(body.models)).catch(() => undefined);
    const hardwareTimer = window.setInterval(() => {
      void api.hardware().then(setHardware).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(hardwareTimer);
  }, []);

  useEffect(() => {
    let stop = false;
    const pull = () => {
      api.tasks(scope).then((body) => {
        if (!stop) setTasks(body.tasks);
      }).catch((reason: Error) => setError(reason.message));
    };
    pull();
    const timer = window.setInterval(pull, 1000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [scope]);

  useEffect(() => {
    if (!activeId) return;
    let stop = false;
    const pull = () => {
      api.task(activeId).then((next) => {
        if (!stop) setTask(next);
      }).catch(() => undefined);
      api.messages(activeId).then((body) => {
        if (!stop) setMessages(body.messages);
      }).catch(() => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 1000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [activeId]);

  useEffect(() => {
    if (task && draftOwner !== task.id) {
      setDraft(task.draft);
      setDraftOwner(task.id);
    }
  }, [task, draftOwner]);

  useEffect(() => {
    if (!task || !draft || draftOwner !== task.id) return;
    const token = `${task.id}:${task.selected_variant_id || ""}`;
    if (token !== laneToken) {
      setLaneToken(token);
      setLaneId(task.selected_variant_id || "source");
    }
  }, [task, draft, draftOwner, laneToken]);

  useEffect(() => {
    if (!draft || !activeId || draftOwner !== activeId) return;
    const timer = window.setTimeout(() => {
      void api.saveDraft(activeId, draft).catch((reason: Error) => setError(reason.message));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [draft, activeId, draftOwner]);

  useEffect(() => {
    stickToBottom.current = true;
  }, [activeId]);

  useEffect(() => {
    const pane = messagePane.current;
    if (!pane || !stickToBottom.current) return;
    pane.scrollTop = pane.scrollHeight;
  }, [messages, activeId]);

  useEffect(() => {
    if (view !== "models") return;
    let stop = false;
    const pull = () => {
      api.models().then((body) => {
        if (stop) return;
        setModels(body.models);
        setModelWarning(body.warning || "");
      }).catch((reason: Error) => setError(reason.message));
      api.downloads().then((body) => {
        if (!stop) setDownloads(body.downloads);
      }).catch(() => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 1000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [view]);

  const lanes = useMemo(() => (task ? buildLanes(task) : []), [task]);
  const selected = task?.variants.find((variant) => variant.id === task.selected_variant_id) || null;
  const changed = Boolean(draft && selected && !sameDraft(draft, selected.spec));
  const playable = selected ? stemOf(selected) : null;
  const origin = task ? laneOrigin(task, laneId) : 0;

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy("upload");
    setError("");
    try {
      const created = await api.upload(file);
      setActiveId(created.id);
      setTask(created);
      setDraft(created.draft);
      setDraftOwner(created.id);
      setScope("all");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败");
    } finally {
      setBusy("");
    }
  }

  function edit(patch: Partial<Draft>, params?: Draft["params"]) {
    setDraft((current) => {
      if (!current) return current;
      return { ...current, ...patch, params: params ? { ...current.params, ...params } : current.params };
    });
  }

  async function preview() {
    if (!task || !draft) return;
    setBusy("preview");
    setError("");
    try {
      await api.preview(task.id, draft, previewKey.current);
      previewKey.current = requestKey();
      setTask(await api.task(task.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "试听失败");
    } finally {
      setBusy("");
    }
  }

  async function run(targets: string[] | null) {
    if (!task) return;
    setBusy("run");
    setError("");
    try {
      await api.run(task.id, changed ? null : task.selected_variant_id, targets, runKey.current);
      runKey.current = requestKey();
      setTask(await api.task(task.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "处理失败");
    } finally {
      setBusy("");
    }
  }

  async function speak(content: string) {
    if (!task || !content.trim()) return;
    setBusy("chat");
    setError("");
    setText("");
    stickToBottom.current = true;
    try {
      const targets = checked.length ? checked : [task.id];
      const body = await api.speak(task.id, content.trim(), targets);
      setMessages(body.messages);
      setTask(body.task);
      setDraft(body.task.draft);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "对话失败");
    } finally {
      setBusy("");
    }
  }

  async function focusVariant(variantId: string) {
    if (!task) return;
    setLaneId(variantId);
    try {
      const next = await api.select(task.id, variantId);
      setTask(next);
      setDraft(next.draft);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法选中方案");
    }
  }

  const gpuName = hardware?.gpu.available ? hardware.gpu.name : "GPU 不可用";
  const engine = health?.inference_blocked ? "推理进程未退出" : health?.torch ? "引擎已连接" : "引擎待确认";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="mark">UVR</div>
          <div>
            <b>UVR Agent WebUI</b>
            <span>本地音频分离工作台</span>
          </div>
        </div>
        <nav className="nav">
          <button className={view === "work" ? "active" : ""} type="button" onClick={() => setView("work")}>工作台</button>
          <button className={view === "models" ? "active" : ""} type="button" onClick={() => setView("models")}>模型库</button>
        </nav>
        <div className="top-status">
          <div className="pill"><i className={health?.inference_blocked ? "dot warn" : "dot"} />{engine}</div>
          <div className="pill">{gpuName}</div>
        </div>
      </header>
      <div className={view === "models" ? "shell models" : "shell"}>
        <aside className="queue">
          <div className="queue-head">
            <h2>任务队列</h2>
            <span className="count">{tasks.length}</span>
          </div>
          <div className="queue-actions">
            <button className="primary wide" type="button" disabled={busy === "upload"} onClick={() => fileRef.current?.click()}>
              新建任务
            </button>
            <input ref={fileRef} className="file" hidden type="file" accept="audio/*,.wav,.flac,.mp3,.ogg,.aiff,.m4a" onChange={(event) => void upload(event.target.files?.[0])} />
          </div>
          <div className="filters">
            {[
              ["all", "全部"],
              ["active", "进行中"],
              ["done", "已完成"],
            ].map(([id, label]) => (
              <button key={id} className={scope === id ? "active" : ""} type="button" onClick={() => setScope(id)}>{label}</button>
            ))}
          </div>
          <div className="task-scroll">
            {tasks.map((item) => (
              <div key={item.id} className={item.id === activeId ? "task active" : "task"}>
                <input
                  className="check"
                  type="checkbox"
                  checked={checked.includes(item.id)}
                  onChange={() => setChecked((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])}
                  aria-label={`选择 ${item.title}`}
                />
                <div>
                  <button type="button" onClick={() => setActiveId(item.id)} style={{ border: 0, background: "transparent", textAlign: "left", padding: 0 }}>
                    <b>{item.title}</b>
                    <small className={item.status.state === "failed" ? "fail" : ""}>
                      {statusLine(item.status)}
                      {item.status.error ? ` · ${item.status.error}` : ""}
                    </small>
                    {item.status.state === "running" && item.status.progress != null ? (
                      <div className="meter"><span style={{ width: `${Math.max(4, item.status.progress)}%` }} /></div>
                    ) : null}
                  </button>
                  <span className="task-actions">
                    {["queued", "running", "waiting_model", "blocked", "paused"].includes(item.status.state) ? (
                      <button type="button" onClick={() => void api.cancel(item.status.job_id).catch((reason: Error) => setError(reason.message))}>取消</button>
                    ) : null}
                    {item.status.state === "paused" ? (
                      <button type="button" onClick={() => void api.continueJob(item.status.job_id).catch((reason: Error) => setError(reason.message))}>继续</button>
                    ) : null}
                    {["failed", "cancelled", "interrupted"].includes(item.status.state) ? (
                      <button type="button" onClick={() => void api.retry(item.status.job_id).catch((reason: Error) => setError(reason.message))}>重试</button>
                    ) : null}
                  </span>
                </div>
              </div>
            ))}
            {tasks.length === 0 ? <div className="empty">还没有任务。上传一首音频开始。</div> : null}
          </div>
          <HardwareCard hardware={hardware} />
        </aside>
        {view === "models" ? (
          <Models
            models={models}
            downloads={downloads}
            warning={modelWarning}
            onDownload={async (arch, name) => {
              await api.downloadModel(arch, name);
              setDownloads((await api.downloads()).downloads);
            }}
          />
        ) : (
          <>
            <main className="stage">
              <div className="stage-inner">
                {!task || !draft || !meta ? (
                  <div className="empty">选择左侧任务，或新建一个。</div>
                ) : (
                  <>
                    <div className="crumb">工作台 / 任务详情</div>
                    <div className="title-row">
                      <div>
                        <h1>{task.title}</h1>
                        <div className="meta">{fileMeta(task)}</div>
                      </div>
                      <button className="ghost" type="button" onClick={() => fileRef.current?.click()}>上传音频</button>
                    </div>
                    {error ? <div className="banner">{error}</div> : null}
                    {task.status.error && task.status.state === "failed" ? <div className="banner">{task.status.error}</div> : null}
                    <Player
                      lanes={lanes}
                      activeId={lanes.some((lane) => lane.id === laneId) ? laneId : "source"}
                      origin={origin}
                      onActive={(id) => {
                        setLaneId(id);
                        if (task.variants.some((variant) => variant.id === id)) void focusVariant(id);
                      }}
                    />
                    <section className="scheme" ref={schemeRef}>
                      <h3>{selected ? `${selected.label} · ${selected.spec.summary}` : "处理方案"}{changed ? " · 参数已改，下次运行会生成新方案" : ""}</h3>
                      <div className="fields">
                        <div className="field">分离模型
                          <MenuSelect
                            label="分离模型"
                            value={modelChoice(draft, meta)}
                            onChange={(value) => {
                              if (value.startsWith("preset:")) {
                                const preset = meta.presets.find((item) => item.id === value.slice(7));
                                if (!preset) return;
                                edit({
                                  arch: preset.arch,
                                  model_name: preset.model_name,
                                  output_target: preset.output_target,
                                  primary_stem: preset.primary_stem,
                                  summary: preset.summary,
                                }, preset.params);
                                return;
                              }
                              const [, arch, name] = value.split(":");
                              const row = models.find((model) => model.arch === arch && model.name === name);
                              const allowed = outputMenu(arch, name, row?.outputs);
                              const primary = allowed.find((item) => item !== "all") || "vocals";
                              edit({
                                arch,
                                model_name: name,
                                output_target: allowed.includes(draft.output_target) ? draft.output_target : allowed[0],
                                primary_stem: primary,
                              }, defaultsFor(arch, draft.params.wav_type));
                            }}
                            groups={[
                              { label: "推荐预设", options: meta.presets.map((preset) => ({ value: `preset:${preset.id}`, label: preset.summary })) },
                              { label: "已安装模型", options: models.filter((model) => model.installed).map((model) => ({ value: `model:${model.arch}:${model.name}`, label: model.name })) },
                            ]}
                          />
                        </div>
                        <div className="field">导出格式
                          <MenuSelect
                            label="导出格式"
                            value={String(draft.params.wav_type || "PCM_24")}
                            onChange={(value) => edit({}, { wav_type: value })}
                            groups={[{ options: meta.wav_types.map((item) => ({ value: item, label: item === "PCM_24" ? "WAV · 24-bit" : "WAV · 16-bit" })) }]}
                          />
                        </div>
                        <div className="field">输出音轨
                          <MenuSelect
                            label="输出音轨"
                            value={draft.output_target}
                            onChange={(value) => edit({ output_target: value })}
                            groups={[{ options: outputMenu(draft.arch, draft.model_name, models.find((model) => model.arch === draft.arch && model.name === draft.model_name)?.outputs).map((item) => ({ value: item, label: TARGET_LABEL[item] || item })) }]}
                          />
                        </div>
                        <QualityField draft={draft} onChange={(params) => edit({}, params)} />
                      </div>
                      <div className="fields" style={{ marginTop: 10 }}>
                        <label className="field">试听起点（秒）
                          <input type="number" min={0} step={0.1} value={draft.start_sec} onChange={(event) => edit({ start_sec: Number(event.target.value) })} />
                        </label>
                        <label className="field">试听终点（秒）
                          <input type="number" min={0} step={0.1} value={draft.end_sec} onChange={(event) => edit({ end_sec: Number(event.target.value) })} />
                        </label>
                      </div>
                      <p className="hint">{selected ? selected.reason : "默认先做一版试听。要比较时再生成下一个方案。"}</p>
                      <div className="run-row">
                        <button className="primary" type="button" disabled={busy === "run"} onClick={() => void run(null)}>
                          {selected && !changed ? `使用${selected.label}处理整首` : "按当前参数处理整首"}
                        </button>
                        <button className="ghost" type="button" disabled={busy === "preview"} onClick={() => void preview()}>生成试听</button>
                        {playable ? <a className="ghost" href={`/api/artifacts/${playable.id}/audio`}>下载</a> : null}
                      </div>
                    </section>
                  </>
                )}
              </div>
            </main>
            <aside className="agent">
              <div className="panel-head">
                <h2>UVR Agent</h2>
                <span className="count">{task ? "当前任务" : "未选择"}</span>
              </div>
              {health && !health.llm_configured ? <p className="note">还没有配置语言模型。试听和整首按钮可以先用；对话需要 agent_web/config.json。</p> : null}
              {task ? <p className="note">围绕「{task.title}」继续。切换任务时，对话会一起换。</p> : null}
              <div
                className="messages"
                ref={messagePane}
                onScroll={(event) => {
                  const pane = event.currentTarget;
                  const distance = pane.scrollHeight - pane.scrollTop - pane.clientHeight;
                  stickToBottom.current = distance < 48;
                }}
              >
                {messages.length === 0 ? (
                  <div className="suggestions">
                    {["做一版 30 秒伴奏试听", "提取人声，先听前 30 秒"].map((prompt) => (
                      <button key={prompt} type="button" disabled={!task || busy === "chat"} onClick={() => void speak(prompt)}>{prompt}</button>
                    ))}
                  </div>
                ) : messages.map((message) => (
                  <article key={message.id} className={`bubble ${message.role}`}>
                    <Markdown text={message.content} />
                    {message.refs?.length ? (
                      <div className="refs">
                        {message.refs.map((ref) => (
                          <button key={ref.id} type="button" onClick={() => ref.variant_id && void focusVariant(ref.variant_id)}>
                            定位到结果
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
                <div />
              </div>
              <div className="quick">
                <button type="button" disabled={!task || busy === "run"} onClick={() => void run(null)}>处理整首</button>
                <button type="button" disabled={!task || busy === "chat"} onClick={() => void speak("换个模型，再做一版试听")}>换个模型</button>
                <button type="button" disabled={!task} onClick={() => schemeRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>查看参数</button>
              </div>
              <form className="composer" onSubmit={(event) => { event.preventDefault(); void speak(text); }}>
                <textarea
                  value={text}
                  placeholder={task ? "描述你的处理需求…" : "先上传音频"}
                  disabled={!task || busy === "chat"}
                  onChange={(event) => setText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void speak(text);
                    }
                  }}
                />
                <div className="composer-row">
                  <span className="note">结果出现在中间的波形里，这里只保留对话。</span>
                  <button className="primary" type="submit" disabled={!task || busy === "chat" || !text.trim()}>发送</button>
                </div>
              </form>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}

function HardwareCard({ hardware }: { hardware: Hardware | null }) {
  const gpu = hardware?.gpu;
  return (
    <section className="hardware">
      <header>
        <span>本地运行</span>
        <span>{hardware?.sampled_at ? hardware.sampled_at.slice(11, 19) : "采样中"}</span>
      </header>
      <strong>{gpu?.available ? gpu.name : "GPU 不可用"}</strong>
      <dl>
        <dt>GPU</dt>
        <dd>{gpu?.available && gpu.utilization != null ? `${gpu.utilization}%` : "不可用"}</dd>
        <dt>显存</dt>
        <dd>{gpu?.available ? `${gigabytes(gpu.memory_used)} / ${gigabytes(gpu.memory_total)} GB` : "不可用"}</dd>
        <dt>CPU</dt>
        <dd>{hardware?.cpu_percent == null ? "不可用" : `${hardware.cpu_percent}%`}</dd>
        <dt>内存</dt>
        <dd>{hardware ? `${gigabytes(hardware.memory_used)} / ${gigabytes(hardware.memory_total)} GB` : "不可用"}</dd>
      </dl>
    </section>
  );
}

function QualityField({ draft, onChange }: { draft: Draft; onChange: (params: Draft["params"]) => void }) {
  if (draft.arch === "vr") {
    return (
      <div className="field">处理强度
        <MenuSelect
          label="处理强度"
          value={String(draft.params.aggression ?? 5)}
          onChange={(value) => onChange({ aggression: Number(value) })}
          groups={[{ options: [1, 5, 10, 20].map((value) => ({ value: String(value), label: `aggression ${value}` })) }]}
        />
      </div>
    );
  }
  if (draft.arch === "demucs") {
    return (
      <div className="field">处理强度
        <MenuSelect
          label="处理强度"
          value={String(draft.params.shifts ?? 2)}
          onChange={(value) => onChange({ shifts: Number(value) })}
          groups={[{ options: [0, 1, 2, 5].map((value) => ({ value: String(value), label: `shifts ${value}` })) }]}
        />
      </div>
    );
  }
  return (
    <div className="field">处理强度
      <MenuSelect
        label="处理强度"
        value={String(draft.params.overlap ?? 0.25)}
        onChange={(value) => onChange({ overlap: Number(value) })}
        groups={[{ options: [0.25, 0.5, 0.75, 0.9].map((value) => ({ value: String(value), label: `overlap ${value}` })) }]}
      />
    </div>
  );
}

function MenuSelect({
  label,
  value,
  groups,
  onChange,
}: {
  label: string;
  value: string;
  groups: { label?: string; options: { value: string; label: string }[] }[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  const current = groups.flatMap((group) => group.options).find((option) => option.value === value);
  return (
    <div className={open ? "menu-select open" : "menu-select"} ref={root}>
      <button type="button" className="menu-trigger" aria-haspopup="listbox" aria-expanded={open} aria-label={label} onClick={() => setOpen((shown) => !shown)}>
        <span>{current?.label ?? value}</span>
      </button>
      {open ? (
        <div className="menu-pop" role="listbox" aria-label={label}>
          {groups.map((group) => (
            <div key={group.label || "items"}>
              {group.label ? <div className="menu-label">{group.label}</div> : null}
              {group.options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  className={option.value === value ? "on" : ""}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function modelChoice(draft: Draft, meta: Meta): string {
  const preset = meta.presets.find((item) => (
    item.arch === draft.arch
    && item.model_name === draft.model_name
    && item.output_target === draft.output_target
    && sameParams(item.params, draft.params)
  ));
  return preset ? `preset:${preset.id}` : `model:${draft.arch}:${draft.model_name}`;
}

function defaultsFor(arch: string, wav: Draft["params"][string] | undefined): Draft["params"] {
  const wavType = typeof wav === "string" ? wav : "PCM_24";
  if (arch === "vr") return { window_size: 512, aggression: 5, tta: false, batch_size: 1, wav_type: wavType };
  if (arch === "demucs") return { shifts: 2, overlap: 0.25, batch_size: 1, wav_type: wavType };
  return { segment_size: 256, overlap: 0.25, batch_size: 1, wav_type: wavType };
}

function sameParams(left: Draft["params"], right: Draft["params"]): boolean {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if (String(left[key]) !== String(right[key])) return false;
  }
  return true;
}

function sameDraft(draft: Draft, spec: Draft): boolean {
  return draft.arch === spec.arch && draft.model_name === spec.model_name && draft.output_target === spec.output_target && sameParams(draft.params, spec.params);
}

function bestJob(variant: Variant): Job | null {
  const ready = variant.jobs.filter((job) => job.status === "succeeded");
  return ready.find((job) => job.kind === "full") || ready.find((job) => job.kind === "preview") || null;
}

function stemOf(variant: Variant) {
  const job = bestJob(variant);
  const stems = job?.artifacts.filter((artifact) => artifact.role === "stem") || [];
  const target = variant.spec.output_target;
  const pattern = target === "vocals" ? /vocal/i : target === "instrumental" ? /instrument|karaoke/i : null;
  return (pattern && stems.find((artifact) => pattern.test(artifact.label))) || stems[0] || null;
}

function buildLanes(task: Task): LaneModel[] {
  const lanes: LaneModel[] = [{ id: "source", title: "原曲", detail: sourceDetail(task), url: sourceUrl(task) }];
  if (task.variants.length === 0) {
    lanes.push({
      id: "pending",
      title: "试听结果",
      detail: task.status.state === "empty" ? "提交后出现" : statusLine(task.status),
      url: "",
      empty: task.status.state === "empty" ? "还没有试听结果" : statusLine(task.status),
    });
    return lanes;
  }
  task.variants.forEach((variant) => {
    const stem = stemOf(variant);
    const latest = variant.jobs[variant.jobs.length - 1];
    lanes.push({
      id: variant.id,
      title: variant.label,
      detail: variant.spec.summary || variant.spec.model_name,
      url: stem ? `/api/artifacts/${stem.id}/audio` : "",
      empty: latest ? `${statusLine(jobStatus(latest))}${latest.error ? ` · ${latest.error}` : ""}` : "还没有结果",
    });
  });
  return lanes;
}

function jobStatus(job: Job) {
  return {
    state: job.hold ? "paused" : job.stage === "waiting_model" ? "waiting_model" : job.status,
    progress: job.progress,
    stage: job.stage,
    error: job.error,
    note: job.note,
    kind: job.kind,
    job_id: job.id,
  };
}

function sourceUrl(task: Task): string {
  const selected = task.variants.find((variant) => variant.id === task.selected_variant_id);
  const job = selected ? bestJob(selected) : null;
  const clip = job?.artifacts.find((artifact) => artifact.role === "source_clip");
  return clip ? `/api/artifacts/${clip.id}/audio` : `/api/tasks/${task.id}/source`;
}

function sourceDetail(task: Task): string {
  const selected = task.variants.find((variant) => variant.id === task.selected_variant_id);
  const job = selected ? bestJob(selected) : null;
  if (job?.kind === "preview" && job.start_sec != null && job.end_sec != null) return `${clock(job.start_sec)} – ${clock(job.end_sec)}`;
  return "与结果同一段";
}

function laneOrigin(task: Task, laneId: string): number {
  const variant = task.variants.find((item) => item.id === laneId) || task.variants.find((item) => item.id === task.selected_variant_id);
  const job = variant ? bestJob(variant) : null;
  if (job?.kind === "preview" && job.start_sec != null && job.artifacts.some((artifact) => artifact.role === "source_clip")) return job.start_sec;
  return 0;
}

function fileMeta(task: Task): string {
  const rate = task.sample_rate ? `${(task.sample_rate / 1000).toFixed(1)} kHz` : "采样率未知";
  const channels = task.channels === 2 ? "立体声" : task.channels ? `${task.channels} 声道` : "声道未知";
  return `${task.filename} · ${rate} · ${channels} · ${clock(task.duration_sec)}`;
}
