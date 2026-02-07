# 🤝 Contributing to UVR Headless Runner

[English](#english) | [中文](#中文)

---

## 中文

感谢你考虑为 UVR Headless Runner 做贡献！无论是 Bug 报告、功能建议还是代码贡献，我们都非常欢迎。

### 如何贡献

#### 🐛 报告 Bug

1. 先搜索 [已有 Issues](https://github.com/chyinan/uvr-headless-runner/issues)，避免重复
2. 使用 [Bug Report 模板](https://github.com/chyinan/uvr-headless-runner/issues/new?template=bug_report.yml) 提交
3. 尽量提供完整信息：命令、错误输出、环境信息

#### ✨ 提出建议

1. 使用 [Feature Request 模板](https://github.com/chyinan/uvr-headless-runner/issues/new?template=feature_request.yml)
2. 描述你想解决的问题，而不仅仅是你想要的功能

#### 🔧 提交代码

1. **Fork** 本仓库
2. 创建你的功能分支：`git checkout -b feature/my-feature`
3. 提交改动：`git commit -m "feat: add my feature"`
4. 推送到你的 Fork：`git push origin feature/my-feature`
5. 创建 **Pull Request**

### 开发环境搭建

```bash
# 克隆你的 Fork
git clone https://github.com/<your-username>/uvr-headless-runner.git
cd uvr-headless-runner

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install pytest

# 运行测试
pytest tests/ -v
```

### 代码规范

- **Python 3.9** — 与上游 UVR GUI 保持一致
- 函数和类需要有 docstring
- 新功能尽量添加对应的测试
- commit message 建议使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：
  - `feat:` 新功能
  - `fix:` Bug 修复
  - `docs:` 文档
  - `refactor:` 重构
  - `test:` 测试

### 项目结构

```
├── mdx_headless_runner.py    # MDX-Net / Roformer / SCNet Runner
├── demucs_headless_runner.py # Demucs Runner
├── vr_headless_runner.py     # VR Architecture Runner
├── model_downloader.py       # 模型下载管理
├── error_handler.py          # 错误处理
├── progress.py               # CLI 进度显示
├── separate.py               # 分离逻辑（上游代码）
├── docker/                   # Docker 部署
├── tests/                    # 自动测试
└── models/                   # 模型配置（非模型文件）
```

> ⚠️ `separate.py`、`lib_v5/`、`demucs/` 是上游 UVR GUI 代码，除非必要请勿修改。

---

## English

Thanks for considering contributing to UVR Headless Runner! We welcome bug reports, feature suggestions, and code contributions.

### How to Contribute

#### 🐛 Report a Bug

1. Search [existing Issues](https://github.com/chyinan/uvr-headless-runner/issues) first
2. Use the [Bug Report template](https://github.com/chyinan/uvr-headless-runner/issues/new?template=bug_report.yml)
3. Include: full command, error output, and environment info

#### ✨ Suggest a Feature

1. Use the [Feature Request template](https://github.com/chyinan/uvr-headless-runner/issues/new?template=feature_request.yml)
2. Describe the problem you want to solve, not just the feature you want

#### 🔧 Submit Code

1. **Fork** the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m "feat: add my feature"`
4. Push to your fork: `git push origin feature/my-feature`
5. Open a **Pull Request**

### Development Setup

```bash
git clone https://github.com/<your-username>/uvr-headless-runner.git
cd uvr-headless-runner
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

### Code Guidelines

- **Python 3.9** — aligned with upstream UVR GUI
- Add docstrings to functions and classes
- Add tests for new features when possible
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages

### Project Architecture

- `*_headless_runner.py` — CLI runners (our code)
- `model_downloader.py` — model registry & downloads (our code)
- `error_handler.py` / `progress.py` — shared utilities (our code)
- `separate.py`, `lib_v5/`, `demucs/` — upstream UVR code (avoid modifying)
- `docker/` — container deployment

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
