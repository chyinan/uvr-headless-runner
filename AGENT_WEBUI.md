# 网页工作台与单 Agent

这一层加在现有 CLI 和分离引擎旁边。网页和 Agent 共用同一个任务服务；分离仍由原来的 Runner 完成。

## 环境

需要两套 Python，不要为了网页去升级原来的音频依赖。

- 控制服务：单独的 Python 3.11 虚拟环境，不要装进系统解释器。

```text
py -3.11 -m venv agent_web/.venv
agent_web\.venv\Scripts\python -m pip install -r agent_web/requirements.txt
```
- 推理：项目目前兼容的 Python 3.9 或 3.10 环境，里面已经有 PyTorch 和音频依赖。
- 前端：Node.js。在 `webui/` 执行 `npm install` 和 `npm run build`。

## 配置

复制 `agent_web/config.example.json` 为 `agent_web/config.json`。这个文件已被忽略，不要把密钥提交进去。

- `inference_python`：推理解释器。Windows 上如果要用启动器，写成 `["py", "-3.10"]`。
- `device`：`auto`、`gpu` 或 `cpu`。`auto` 在能读到 NVIDIA 显卡时使用 GPU。
- `data_dir`：留空时使用 `agent_web/data`。任务、数据库和产物都在这里。
- `llm`：一种 OpenAI 兼容的对话接口。`api_key` 为空时，手动按钮仍可用，对话会说明尚未配置。

模型文件继续放在仓库的 `models/` 目录，和现有下载器一致。

## 启动

在仓库根目录：

```text
agent_web\.venv\Scripts\python -m agent_web
```

浏览器打开 `http://127.0.0.1:8787`。开发界面可以另开 `webui` 里的 `npm run dev`，它会把 `/api` 代理到 `8787`。

服务只监听本机。全应用同时只跑一个分离进程；模型下载单独进行，不占用这个推理槽。

## 使用

上传音频后默认先做一版试听，通常是前 30 秒。明确要求调整或比较之后才会出现下一个方案。说“处理整首”或点处理按钮会直接开始，不会再问一次。批量时先在左侧勾选已经上传的任务，再把当前方案应用到这些文件；每首歌各有自己的任务和产物，推理串行执行。

推荐预设写在 `agent_web/presets.json`。目前是 Inst HQ 3 的两个 overlap，以及 Voc FT。overlap、VR aggression 和 Demucs shifts 才会被当作音质相关参数。

## 验收记录

2026-11-13 在当前开发机上核对：

| 项 | 结果 |
| --- | --- |
| 服务规则单测 | 通过。覆盖单版试听、重复提交、调整门槛、batch size、整首与两文件批量、取消、重启暂停、失败重试、模型等待、Agent 提交和 LLM 失败隔离。 |
| 既有 CLI | `py -3.11 cli.py help` 可以运行，网页依赖没有进入 CLI。 |
| 前端构建 | `webui` 的类型检查和生产构建通过。 |
| A1 真实分离 | 需要本机推理环境、模型和音频。本轮没有把模拟结果当成分离通过。 |
| A6 真实下载 | 需要联网访问官方模型源，在目标机器上点一次未安装模型。 |
| A7 硬件卡 | 这台机器已读到 RTX 5070 Ti、显存、CPU 和系统内存，并在页面上按约 3 秒刷新。 |
| A8 干净启动 | 按上面的配置从新终端启动。推理环境要能 `import torch`。 |

已知限制：Demucs 没有单独的伴奏轨，做伴奏用 MDX Inst 模型。试听和整首使用同一套参数，短片段和全曲的上下文并不保证听感完全一致。服务重启后，正在运行的任务标为已中断，原来的排队任务暂停，需要手动继续。

2026-11-14 又在浏览器里核对了工作台。任务列表、试听空状态、原曲播放和结束、切换任务时对话一起切换、模型库筛选都可用。硬件卡读到 RTX 5070 Ti、显存、CPU 和内存。官方目录返回 103 个模型，本机 `models/` 里还没有权重，真实分离和真实下载仍待在这台机器上做。未配置语言模型时，对话只说明原因，不会创建试听任务。

这台机器的 `py -3.11` 能跑控制服务，但缺少音频依赖。`C:\Python314\python.exe` 有 CUDA 版 PyTorch，但缺少 `julius`，不能直接当作推理解释器。找到能导入现有 Runner 的解释器后，写入 `agent_web/config.json` 的 `inference_python`，再重启服务。
