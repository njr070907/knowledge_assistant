# 知流（Zhiliu）

[![CI](https://github.com/njr070907/knowledge_assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/njr070907/knowledge_assistant/actions/workflows/ci.yml)

知流是一个本地优先的实时视频学习助手。目前已经接通：

- Chrome / Edge 标签页音频捕获
- 16 kHz 单声道 PCM 实时传输
- 本机 `faster-whisper` 转写
- 扩展侧栏中的实时字幕、播放状态和暂停回忆界面
- SQLite 会话与逐字稿保存
- 面向真实课程音频的 ASR 基准测试
- 高数、线代、马原、一生一芯自动分类
- 带时间戳的实时知识卡片
- 课后 Markdown、主动回忆题与 1/3/7 天复习任务
- 可选本地 `llama.cpp` 二次整理
- Notion Markdown 同步队列与失败重试

原始音频与逐字稿默认只留在本机。即使没有配置 Notion，课后笔记也会写入 `server/data/notes/`。

## 项目结构

```text
extension/   Chromium MV3 扩展与 React 侧栏
server/      本机 FastAPI、WebSocket、ASR 与 SQLite
docs/design/ 界面概念稿
```

## 1. 启动本机服务

需要 Python 3.11 或更高版本。

```powershell
cd D:\codex_project\zhiliu-study-assistant\server
.\scripts\setup.ps1
.\scripts\run.ps1
```

第一次启动会下载 Whisper `small` 多语模型。可通过环境变量调整：

```powershell
$env:ZHILIU_ASR_MODEL = 'medium'
$env:ZHILIU_ASR_DEVICE = 'cpu'
$env:ZHILIU_ASR_COMPUTE_TYPE = 'int8'
.\scripts\run.ps1
```

服务健康检查：<http://127.0.0.1:8765/health>

## 2. 可选：配置本地模型与 Notion

复制配置模板：

```powershell
cd D:\codex_project\zhiliu-study-assistant\server
Copy-Item .env.example .env
notepad .env
```

本地模型默认关闭。若已经启动兼容 OpenAI 接口的 `llama.cpp server`，在 `.env` 中设置：

```text
ZHILIU_LLM_ENABLED=true
ZHILIU_LLM_BASE_URL=http://127.0.0.1:8080/v1
ZHILIU_LLM_MODEL=你的本地模型名
```

知流会拒绝把本地模型地址配置为外网主机，避免逐字稿意外外发。模型不可用时会自动回退到本地规则稿。

Notion 使用当前 `2026-03-11` API。创建个人访问令牌或内部连接，把目标父页面共享给该连接，然后设置：

```text
NOTION_TOKEN=你的令牌
NOTION_PARENT_PAGE_ID=目标页面ID
```

令牌仅保存在 `server/.env`，该文件已被 `.gitignore` 排除。每次课程只上传整理后的 Markdown；失败任务保留在本地，可通过 `POST /api/sync/notion/retry` 重试。

## 3. 构建并加载扩展

需要 Node.js 20 或更高版本。

```powershell
cd D:\codex_project\zhiliu-study-assistant\extension
npm install
npm run build
```

然后打开 Chrome/Edge 扩展管理页，开启开发者模式，选择“加载已解压的扩展”，加载：

```text
D:\codex_project\zhiliu-study-assistant\extension\dist
```

打开 B 站、YouTube 或抖音视频，点击浏览器工具栏中的“知流”。点击动作既是用户授权，也是开始本次学习。再次结束请使用侧栏底部“结束学习”。

## 4. 运行十分钟基准

先准备一段来自真实课程的本地音频或视频文件：

```powershell
cd D:\codex_project\zhiliu-study-assistant\server
.\scripts\benchmark.ps1 -AudioPath 'D:\path\course.mp4' -Model small
```

脚本会输出总耗时、音频时长和实时因子（RTF）。第一阶段目标：

- `RTF < 0.7`
- 稳定字幕延迟约 3–5 秒
- 视频播放不掉帧

## 隐私边界

- 服务仅监听 `127.0.0.1`。
- WebSocket 使用每次会话生成的随机令牌。
- 音频只在内存中分块处理，默认不写入磁盘。
- SQLite 只保存会话元数据、确认后的转写片段和用户标记。

## GitHub 自动化工作流

仓库的 `.github/workflows/ci.yml` 会在推送到 `main` 或提交 Pull Request 时自动执行：

- Python 3.11 后端依赖安装与测试
- Node.js 20 扩展测试、类型检查与正式构建
- 上传可直接加载的 `extension/dist` 构建产物，并保留 14 天

本地 `.env`、虚拟环境、依赖目录、数据库、生成笔记和构建目录均被忽略，不会被提交到仓库。
