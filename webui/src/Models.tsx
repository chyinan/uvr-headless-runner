import { useMemo, useState } from "react";
import type { DownloadRow, ModelRow } from "./api";
import { STAGE_LABEL } from "./api";

export function Models({
  models,
  downloads,
  warning,
  onDownload,
}: {
  models: ModelRow[];
  downloads: DownloadRow[];
  warning: string;
  onDownload: (arch: string, name: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [arch, setArch] = useState("all");
  const [installed, setInstalled] = useState("all");
  const [pending, setPending] = useState("");

  const nameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const model of models) {
      const id = `${model.arch}:${model.name}`;
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
    return counts;
  }, [models]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return models.filter((model) => {
      if (arch !== "all" && model.arch !== arch) return false;
      if (installed === "yes" && model.installed !== true) return false;
      if (installed === "no" && model.installed === true) return false;
      if (!needle) return true;
      return model.name.toLowerCase().includes(needle) || model.display_name.toLowerCase().includes(needle);
    });
  }, [models, query, arch, installed]);

  return (
    <section className="library">
      <div className="library-inner">
        <h2>模型库</h2>
        <p className="meta">官方目录和本机安装状态。下载与推理分开进行，已安装的模型不会被其他下载挡住。</p>
        {warning ? <p className="banner">目录暂时用了本地缓存或预设：{warning}</p> : null}
        <div className="filters-line">
          <label className="search">
            <input value={query} placeholder="搜索模型名称" onChange={(event) => setQuery(event.target.value)} />
          </label>
          {["all", "mdx", "vr", "demucs"].map((item) => (
            <button key={`arch:${item}`} className={arch === item ? "primary" : "ghost"} type="button" onClick={() => setArch(item)}>
              {item === "all" ? "全部架构" : item.toUpperCase()}
            </button>
          ))}
          {["all", "yes", "no"].map((item) => (
            <button key={`status:${item}`} className={installed === item ? "primary" : "ghost"} type="button" onClick={() => setInstalled(item)}>
              {item === "all" ? "安装状态" : item === "yes" ? "已安装" : "未安装"}
            </button>
          ))}
        </div>
        <div className="model-list">
          {visible.map((model) => {
            const job = downloads.find((item) => item.arch === model.arch && item.model_name === model.name);
            const active = job && (job.status === "queued" || job.status === "running");
            const sharedName = (nameCounts.get(`${model.arch}:${model.name}`) ?? 0) > 1;
            return (
              <article className="model" key={`${model.arch}:${model.name}:${model.display_name}:${model.files.join("|")}`}>
                <div>
                  <b>{sharedName ? model.display_name : model.name}</b>
                  <small>
                    <span className="tag">{model.arch}</span>
                    <span className={model.installed ? "tag on" : "tag"}>{model.installed ? "已安装" : "未安装"}</span>
                    {model.executable ? "可提交到当前工作台" : "仅展示"}
                    {active ? ` · ${job.progress == null ? STAGE_LABEL[job.stage] || "下载中" : `${Math.round(job.progress)}%`}` : ""}
                    {job?.status === "failed" ? ` · ${job.error}` : ""}
                  </small>
                </div>
                <button
                  className="ghost"
                  type="button"
                  disabled={model.installed || Boolean(active) || pending === `${model.arch}:${model.name}`}
                  onClick={() => {
                    setPending(`${model.arch}:${model.name}`);
                    void onDownload(model.arch, model.name).finally(() => setPending(""));
                  }}
                >
                  {model.installed ? "已可用" : active ? "下载中" : "下载"}
                </button>
              </article>
            );
          })}
          {visible.length === 0 ? <div className="empty">没有符合条件的模型。</div> : null}
        </div>
      </div>
    </section>
  );
}
