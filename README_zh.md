# Remote Dev Manager (rdm)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Built with Tauri](https://img.shields.io/badge/desktop-Tauri%20v2-24C8DB.svg)](https://tauri.app/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**桌面应用 + 命令行 + 终端 TUI，让你在远程服务器上跑 Claude Code / Codex —— 本地读改远端代码，远端的 AI 流量从你自己的代理出去。**

[English](README.md) | 简体中文

---

## 这是什么

Remote Dev Manager（`rdm`）帮你打理本地和远端开发机之间的所有连接：SSH 隧道、SSHFS 挂载、反向代理隧道、智能代码镜像。它最核心的能力，是为「在远程服务器上使用 AI 编程工具（**Claude Code**、**Codex CLI**）」的开发者设计的：**一键**建立反向隧道，让远端机器把 API 请求绕回你**本机的 Clash 代理**——这样即使服务器在防火墙 / GFW 后面、连不上 `api.anthropic.com` / `api.openai.com`，AI 工具照样能用。再配合**代码镜像**功能，把远端仓库拉到本地目录（自动排除模型权重、数据集、二进制大文件），AI 工具在本地飞快读代码，而服务器仍然是真正的执行环境。

三种用法任选：原生**桌面 GUI**、`rdm` **命令行**、终端 **TUI**。

---

## 截图

> **注意：** 下面是占位图，发布前请把真实截图放进 `docs/screenshots/`。

![Dashboard](docs/screenshots/dashboard.png)
![Hosts](docs/screenshots/hosts.png)
![AI Proxy](docs/screenshots/ai-proxy.png)

---

## 功能

### 桌面 GUI

- 支持 **Windows、macOS、Linux** 的原生应用，基于 **Tauri v2**（Rust 外壳 + React/TypeScript/Vite 前端）。
- 精致的 **shadcn/ui（radix-nova）界面**，支持**浅色 / 深色主题**切换。
- **桌面级体验细节：** 无启动闪屏（界面绘制完成前窗口保持隐藏）、外部链接在系统浏览器中打开、原生滚动与文本选择行为、优化过的 release 二进制。
- **系统托盘**（显示 / 退出）——关闭窗口只是收进托盘，不会真正退出。
- 可选的开机**自启动**。
- 通过 WebSocket 实时推送服务状态和日志；单实例运行。

### 隧道与挂载

- **SSH 隧道**——本地（`-L`）、远程（`-R`）、动态（`-D`）端口转发，带 keepalive 和指数退避的自动重启守护。
- **SSHFS 挂载**——把远端目录挂到本地文件夹，在本地直接读改远端代码。Windows 用 SSHFS-Win + WinFsp，Linux/macOS 用 `sshfs`。
- **反向代理隧道**——通过 SSH `-R` 把本机的 Clash/SOCKS 代理暴露到远端服务器上。
- **SSH 连接本身的代理路由**：`direct`（直连）、走本机 Clash（SOCKS5）、或走 SSH 跳板机。

### AI 代理（招牌功能）

- **一键 AI 代理**——同时完成三件事：建立反向隧道 **+** 在远端写入 `~/.rdm_proxy.sh`（`ALL_PROXY`/`HTTPS_PROXY`/`HTTP_PROXY=socks5://127.0.0.1:7897`）**+** 通过隧道 curl AI 端点验证连通性。
- 自动生成可直接复制运行的 `ssh -t … claude` / `codex` 启动命令。
- 可选写入 `~/.bashrc` 做持久化。

### 代码镜像

- **智能代码镜像**——用 rsync 把远端仓库同步到本地目录，自动排除模型权重、图片、数据集、二进制（内置 107 条规则），并可用 `--max-size` 限制单文件大小。
- 双向 **push / pull**，外加 **browse** 命令扫描远端主机上的仓库。
- **快速文件克隆**——一步 scp 把远端单个文件拉到本地。

### 命令行与 TUI

- 功能完整的 `rdm` 命令行：`up`、`down`、`status`、`log`、`sync`、`mirror`、`init`、`tui`。
- 基于 Textual 的终端 **TUI** 面板，启停 / 重启 / 监控所有服务。

---

## 为什么需要它

它瞄准的是当下用 AI 编程工具的远程开发闭环：

1. **本地读改远端代码。** 用 SSHFS 挂载或 rsync 镜像，让编辑器和 AI 工具读的是本地文件——不用把几个 G 的模型权重、数据集拖过网络。
2. **工具在远端执行。** 服务器仍是真正的执行环境（GPU、数据、各种服务）。
3. **AI 流量走你的代理。** 哪怕服务器连不上 `api.anthropic.com` / `api.openai.com`，反向隧道也会把请求绕回你本机 Clash，Claude Code / Codex 照常工作。

---

## 架构

```
                          桌面应用 (Tauri v2)
   ┌─────────────────────────────────────────────────────────────┐
   │  Rust 外壳  ⇄  React/TS 前端                                  │
   │  (托盘、自启动、       │                                       │
   │   拉起 sidecar)       │  http + ws  →  127.0.0.1:8765         │
   └──────────────────────┼────────────────────────────────────────┘
                          │
                          ▼
              FastAPI sidecar  (python -m rdm.api)
                          │
                          ▼
                      rdm 核心
        (配置 · 进程守护 · 隧道 · 挂载 ·
         代理 · 同步 · 镜像 · 远程 SSH 自动化)
                          │
                          ▼
            系统工具:  ssh · rsync · sshfs · scp
                          │
                          ▼
                       远程服务器

  AI 代理路径:
    远端 AI 工具  →  socks5://127.0.0.1:7897 (远端)
                  →  ssh -R 反向隧道
                  →  本机 Clash :7897  →  互联网
```

三个前端共用同一个 `rdm` 核心。CLI/TUI 在进程内直接调用；桌面应用通过 FastAPI sidecar 走 http/ws 调用。它们读写的都是**同一个 `rdm.yaml`** 配置文件。

---

## 安装

### 1. 桌面应用（推荐）

从 [Releases 页面](https://github.com/your-org/remote-dev-manager/releases) 下载预编译安装包（*占位——尚未发布正式版本*）。

> 挂载和镜像功能仍需要 `PATH` 上有 `ssh`，以及 `rsync` / `sshfs`（平台说明见 [配置文档](docs/configuration.md)）。

### 2. 从源码构建桌面应用

完整开发指南见 **[docs/desktop-app.md](docs/desktop-app.md)**。简版（Windows、macOS、Linux 通用）：

```bash
cd desktop
npm install
npm run tauri dev      # 开发模式（自动拉起 Python sidecar）
```

要在本地打安装包，运行 `scripts/build-desktop.ps1`（Windows）或 `scripts/build-desktop.sh`（macOS/Linux）。要一次性构建三个平台的安装包，推一个 `vX.Y.Z` 标签即可触发 [GitHub 发布工作流](.github/workflows/desktop-build.yml)，自动构建并生成草稿 release。

### 3. 通过 pip 安装命令行 / TUI

```bash
git clone https://github.com/your-org/remote-dev-manager.git
cd remote-dev-manager
pip install -e ".[api]"     # [api] 额外依赖会装上 FastAPI + uvicorn，供 sidecar / `rdm web` 使用
```

---

## 快速上手（桌面）

1. **启动应用。** 它会拉起本机 sidecar 并打开面板。
2. 在 Hosts 页面**添加主机**（user、host、port、密钥）。
3. **测试**连接——应能看到远端用户名、主机名和操作系统。
4. 给该主机**一键开启 AI 代理**，或**添加镜像**把仓库拉到本地。
5. 关闭窗口会收进**系统托盘**；托盘 →「退出」才彻底关闭。

---

## 快速上手（命令行）

```bash
# 在当前目录生成起始配置
rdm init

# 编辑 rdm.yaml —— 填上 hosts、tunnels、mounts、reverse_proxies、mirrors

# 全部启动（或指定服务名）
rdm up
rdm up gpu-jupyter cloud-clash

# 看状态 / 跟日志
rdm status
rdm log gpu-jupyter

# 终端交互面板
rdm tui            # （直接运行 `rdm` 不带参数也会进 TUI）
```

镜像相关命令：

```bash
rdm mirror browse gpu-server                  # 扫描远端仓库
rdm mirror add gpu-server /home/u/proj --name proj
rdm mirror pull proj                          # 远端 → 本地（自动排除权重/数据）
rdm mirror push proj                          # 本地 → 远端
rdm mirror status proj                        # 查看待同步改动
rdm mirror list
```

指定配置文件：`rdm -c /path/to/config.yaml <command>`。

---

## AI 代理工作流

远程服务器经常连不上 `api.anthropic.com` / `api.openai.com`。rdm 的做法是把服务器的代理端口反向隧道回你本机 Clash：

1. **本机跑一个代理**（Clash / mihomo / V2Ray）——一般是 `127.0.0.1:7897` 的 SOCKS5。
2. 在桌面应用里**一键开启 AI 代理**（或命令行 `rdm up <反向代理>`），它会：
   - 启动 `ssh -R 7897:127.0.0.1:7897` 反向隧道；
   - 在远端写入 `~/.rdm_proxy.sh`，导出 SOCKS5 环境变量；
   - 通过隧道 curl AI 端点验证连通性。
3. **在远端启动**并带上代理——rdm 会给你一条可直接复制的命令，例如：
   ```bash
   ssh -t user@host 'source ~/.rdm_proxy.sh; claude'
   ```

流量于是这样走：**远端 AI 工具 → 反向隧道 → 你本机 Clash → 互联网。**

完整深入说明（含 Codex 注意事项和排错）：**[docs/ai-proxy-setup.md](docs/ai-proxy-setup.md)**。

---

## 配置

rdm 由单个 YAML 文件配置，按以下顺序查找：

1. `$RDM_CONFIG`
2. `./rdm.yaml`
3. `~/.config/rdm/config.yaml`（Linux/macOS）或 `%APPDATA%\rdm\config.yaml`（Windows）

**桌面 UI、命令行、TUI 读写的是同一个文件。**

- 带详细注释的示例：**[config.example.yaml](config.example.yaml)**
- 字段完整参考：**[docs/configuration.md](docs/configuration.md)**

---

## 从源码构建

- **桌面应用（Windows / macOS / Linux）：** 见 **[docs/desktop-app.md](docs/desktop-app.md)**（前置依赖、开发流程、发布构建、图标、托盘、排错）。本地构建用 `scripts/build-desktop.ps1` / `scripts/build-desktop.sh`，或推一个 `vX.Y.Z` 标签触发[跨平台发布工作流](.github/workflows/desktop-build.yml)。
- **仅命令行 / TUI：** `pip install -e ".[api]"`。
- **架构参考：** **[docs/architecture.md](docs/architecture.md)**。

---

## 参与贡献

欢迎 PR！开发环境、代码风格和架构概览见 **[CONTRIBUTING.md](CONTRIBUTING.md)**。

## 许可证

[MIT](LICENSE)
