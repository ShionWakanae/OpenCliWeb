<div align="center">
  <img src="res/logo.png" alt="OpenCliWeb" width="120" />
  <h1>OpenCliWeb · 我的小助手</h1>
  <p><strong>用一句自然语言，查询任意网站 —— 基于 OpenCLI 的个人问答助手</strong></p>
  <p>
    <a href="README.md"><strong>简体中文</strong></a> ·
    <a href="README_en.md">English</a>
  </p>
  <p>
    <a href="https://img.shields.io/github/license/ShionWakanae/OpenCliWeb" target="_blank"><img src="https://img.shields.io/github/license/ShionWakanae/OpenCliWeb.svg" alt="MIT License" /></a>
    <a href="https://img.shields.io/github/stars/ShionWakanae/OpenCliWeb?style=social" target="_blank"><img src="https://img.shields.io/github/stars/ShionWakanae/OpenCliWeb?style=social" alt="Stars" /></a>
    <img src="https://img.shields.io/badge/Python-3.10-blue?logo=Python" alt="Python 3.10" />
    <img src="https://img.shields.io/badge/Node.js-21%2B-green?logo=Node.js" alt="Node.js 21+" />
    <img src="https://img.shields.io/badge/WebUI-NiceGUI-64b5cf" alt="NiceGUI" />
    <img src="https://img.shields.io/badge/LLM-OpenAI%20compatible-412991" alt="OpenAI compatible" />
    <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT" />
  </p>
</div>

---

> 用自然语言查询各个网站，基于 [OpenCLI](https://github.com/jackwener/opencli)。
> 因为调用时使用的是**你自己的浏览器登录态**，所以它更像一个"个人小助理"，而不是一个公共爬虫。

## 目录

- [这是什么](#这是什么)
- [核心特性](#核心特性)
- [与直接使用 OpenCLI 的区别](#与直接使用-opencli-的区别)
- [界面预览](#界面预览)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [工作原理](#工作原理)
- [配置项](#配置项)
- [支持的站点](#支持的站点)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [视频演示](#视频演示)
- [致谢](#致谢)
- [许可证](#许可证)
- [参与贡献](#参与贡献)

## 这是什么

OpenCliWeb 是一个把 [OpenCLI](https://github.com/jackwener/opencli) 包装成对话助手的 Web 项目。

OpenCLI 本身提供了一批"网站适配器"（site adapter），能把 B 站、知乎、12306、arXiv、携程…… 这类网站变成可以命令行调用的接口。你只需要用自然语言提一个需求，本项目负责让 LLM 判断该调用哪些命令、按什么顺序调用、怎么把结果组织成一段可读的答案。

两个入口，任选其一：

- **命令行**：一句 `python src/open_cli.py "你的问题"`，适合脚本化与快速查询。
- **WebUI**：NiceGUI 写的聊天界面，展示推理过程与工具调用轨迹，适合日常使用。

WebUI 沿用了作者的另一个项目 [Llamarkdown](https://github.com/ShionWakanae/Llamarkdown) 的界面。

## 核心特性

1. **由 LLM 规划调用顺序** —— 不需要你记住每个站点的命令格式，模型会先查帮助、再执行。
2. **执行过程完全可见** —— 每一次 `site_help` / `cmd_exec` 调用及其返回都在 WebUI 的「执行过程」面板里展开。
3. **零学习成本** —— 用户只需提出问题或需求，其余交给智能体。
4. **主动提示可用站点** —— 主页用星环展示所有可用 site 及其用途，点击即填入提问框。
5. **站点描述缓存** —— 启动时自动为站点生成一句话用途说明并落盘缓存，显著提升模型选对站点的成功率。
6. **结果自动瘦身** —— 裁剪条数、剔除噪音字段、针对特定站点做特殊处理，显著节省 token。
7. **在线 / 本地 LLM 均可** —— 任何 OpenAI 兼容端点都行，包括 llama.cpp、Ollama 等本地部署。
8. **自带护栏** —— 重复命令拦截、工具循环上限、超时保护，避免模型空转烧钱。

## 与直接使用 OpenCLI 的区别

**和直接敲 OpenCLI 命令行相比：**

1. 由 LLM 判断并编排该调用哪些命令、什么顺序。
2. 可以在 WebUI 里查看调用多个命令的详细过程。
3. 你只需要提出问题或需求。
4. 主动提示所有可操作的 site 以及帮助示例。
5. 缓存站点列表及描述，提高查询成功率。

**和用 Agent 通过 skill 调用 OpenCLI 相比：**

1. 简化了操作流程和数据结构，只聚焦"网站（site）"这一类目标。
2. 用在线 LLM 可以省下大量 token。
3. 用本地 LLM 更容易稳定地"Hold 住"并完成任务。
4. 大概相当于自行车和汽车的差别：下坡省力，上坡省油。

## 界面预览

| 主界面（星环站点浏览器） | 对话与工具调用 |
| --- | --- |
| ![主界面](res/webui_0.png) | ![对话界面](res/webui.png) |

![执行过程与结果](res/webui_1.png)

## 环境要求

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| Node.js | ≥ 21.0.0（或 Bun ≥ 1.0） | OpenCLI 的运行前提；项目启动时只校验 `node` 命令是否可用 |
| Python | 3.10（作者验证过的版本） | 3.11 及以上尚未测试 |
| Chrome / Chromium | 较新版本 | 需要登录目标网站，并安装 OpenCLI 的 Browser Bridge 扩展 |
| OpenCLI | 最新版 | `npm install -g @jackwener/opencli` |
| LLM API | 任意 OpenAI 兼容端点 | 在线（OpenAI 等）或本地（llama.cpp / Ollama 等） |

> OpenCLI 的完整安装说明见官方文档：[中文版](https://opencli.info/docs/zh/guide/installation.html) / [English](https://opencli.info/docs/guide/installation.html)。

## 快速开始

### 1. 安装 OpenCLI

```powershell
npm install -g @jackwener/opencli
```

然后安装浏览器扩展，二选一：

- **Chrome 应用商店**（推荐）：[安装 OpenCLI 扩展](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)。
- **手动安装**：从 [GitHub Releases](https://github.com/jackwener/opencli/releases) 下载 `opencli-extension-v{version}.zip`，解压后在 `chrome://extensions` 开启开发者模式，选择「加载已解压的扩展程序」。详见 [Browser Bridge 指南](https://opencli.info/docs/zh/guide/browser-bridge.html)。

装好后用下面的命令自检，三项都应显示 OK：

```powershell
opencli doctor
```

项目启动时也会自动执行一次 `opencli doctor`。如果检测到某个浏览器 profile 没有连接，会尝试执行 `opencli profile use <profile>` 后重试。

### 2. 克隆仓库并安装依赖

```powershell
git clone https://github.com/ShionWakanae/OpenCliWeb.git
cd OpenCliWeb
python -m venv venv
.\venv\scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
copy .env_sample .env      # Windows
```

```bash
cp .env_sample .env        # macOS / Linux
```

编辑 `.env`，至少填写 `STORAGE_SECRET`、`LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL` 四项 —— 缺任意一项都会在启动时直接报错退出。建议同时设置 `WEBUI_USERNAME` / `WEBUI_PASSWORD`，否则无法登录 WebUI。完整说明见[配置项](#配置项)。

### 4. 启动

> ⚠️ 务必在**项目根目录**执行。项目内部使用相对路径读取 `data/` 与 `src/ui/`，在子目录下运行会找不到站点缓存和静态资源。

命令行模式：

```powershell
python .\src\open_cli.py "B站最热门的5条视频"
```

WebUI 模式：

```powershell
python .\src\open_web.py
```

然后打开浏览器访问 <http://127.0.0.1:7860/>，用 `.env` 中的账号密码登录。

也可以直接用仓库自带的一键脚本（会自动激活虚拟环境）：

```powershell
.\run_cli.ps1        # 命令行
.\run_webui.ps1      # WebUI
```

## 使用方式

### 命令行模式

```powershell
python .\src\open_cli.py "你的问题" [--Think] [--Verbose]
```

| 参数 | 作用 |
| --- | --- |
| `--Think` | 开启推理模式，模型的思考过程会单独流式输出；关闭时向模型请求禁用 thinking |
| `--Verbose` | 输出详细日志：模型名、工具调用、耗时、token 统计等 |

终端会依次输出：问题回显 → 工具调用轨迹 → 最终答案 → 耗时统计（Retrieval / Answers / Total）→ token 进出量与生成速度。

### WebUI 模式

| 功能 | 说明 |
| --- | --- |
| 登录页 | 使用 `.env` 中的 `WEBUI_USERNAME` / `WEBUI_PASSWORD` |
| 星环主页 | 每一颗星是一个可用 site，悬停显示用途，点击自动填入提问框 |
| 快捷提问 | 顶部一行示例问题，一键发送 |
| 推理开关 | 右上角「推理」开关，等价于命令行的 `--Think` |
| 执行过程面板 | 每次回答旁的「执行过程」折叠区，实时显示模型阶段、工具调用与返回内容 |
| 答案渲染 | 支持 Markdown 与 MathJax 公式 |
| 会话管理 | 菜单可清空会话 / 退出登录；聊天记录按用户保存在 NiceGUI storage，刷新不丢失 |
| 状态显示 | 每条回答右下角显示模型名、耗时、速度标识与时间戳 |

## 工作原理

```
用户提问
   │
   ▼
┌───────────────┐   系统提示词内置「站点清单 + 工具定义」
│  ① LLM 规划    │   site_help / cmd_exec
└───────┬───────┘
        │  匹配站点：把用户意图映射到最接近的 site
        ▼
┌───────────────┐   opencli <site> --help
│ site_help(site)│  → 返回该站点的全部命令与参数
└───────┬───────┘
        │  ② 拼接完整命令串（不拼 opencli / cmd / -f）
        ▼
┌───────────────┐   opencli <site> <cmd> ... -f yaml
│ cmd_exec(cmd)  │  → 真实数据（按 JSON / YAML 解析）
└───────┬───────┘
        │  ③ 结果清洗：裁剪条数、剔除噪音字段、站点特例处理
        ▼
┌───────────────┐   按 LANGUAGE 输出 Markdown 答案
│   组织答案      │
└───────────────┘
```

**两个工具**

- `site_help(site)` —— 列出单个站点的全部可用命令与参数。
- `cmd_exec(full_cmd, result_trim?)` —— 执行一条完整的站点命令。

**关键设计**

- **命令去重**：完全相同的命令被重复执行时会直接拦截并返回提示，避免模型反复空转。
- **循环保护**：同一工具 + 同一参数调用超过 5 次，或总轮次超过 99 次，立即中止并向用户说明。
- **结果裁剪**：优先使用命令自身的 `--limit`；命令不支持时可用 `result_trim` 截断返回条数。
- **字段精简**：自动剔除 `image_url`、`browser`、`domain`、`access` 等与回答无关的字段以节省 token。
- **站点特例**：toutiao 会清理 URL 查询参数；12306 会移除"是否有余票"字段，避免模型误判。
- **两种工具调用格式**：既支持标准 function calling，也兼容部分模型直接输出 XML 形式的工具调用。
- **站点清单缓存**：站点列表来自 `opencli --help`，启动时为每个站点生成一句用途描述并缓存到 `data/sites_metadata.json`，之后只做增量维护。

## 配置项

在 `.env` 中配置，完整样例见 [`.env_sample`](.env_sample)。

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `STORAGE_SECRET` | ✅ | — | NiceGUI 会话存储密钥，填任意固定字符串 |
| `LLM_API_BASE` | ✅ | — | OpenAI 兼容 API 地址，如 `https://api.openai.com/v1` 或本地 `http://127.0.0.1:8080/v1` |
| `LLM_API_KEY` | ✅ | — | API 密钥 |
| `LLM_MODEL` | ✅ | — | 模型名，如 `gpt-4.1-mini`；需支持 function calling |
| `WEBUI_USERNAME` | 建议 | — | WebUI 登录用户名；未设置时无法登录 |
| `WEBUI_PASSWORD` | 建议 | — | WebUI 登录密码 |
| `HOST` | | `0.0.0.0` | WebUI 监听地址；`.env_sample` 中为 `127.0.0.1`（仅本机可访问） |
| `PORT` | | `7860` | WebUI 端口 |
| `LANGUAGE` | | `简体中文` | 回答所用语言，英文使用填 `English` |

## 支持的站点

站点清单由 OpenCLI 决定，随上游版本变化，当前约 160 个。下面是按用途归类的常见示例：

| 分类 | 示例 |
| --- | --- |
| 社交 / 社区 | bilibili、weibo、zhihu、xiaohongshu、reddit、v2ex、tieba、hupu、jike、linux-do |
| 视频 / 音频 | youtube、douyin、tiktok、spotify、suno、apple-podcasts、wechat-channels |
| 资讯 / 财经 | toutiao、36kr、sinafinance、eastmoney、reuters、bbc、bloomberg、xueqiu |
| 学术 / 论文 | arxiv、dblp、pubmed、openalex、semanticscholar、cnki、wanfang、paperreview |
| 技术 / 开发 | github、gitee、stackoverflow、npm、pypi、dockerhub、maven、mdn、nvd、endoflife |
| 生活 / 服务 | ctrip、12306、dianping、taobao、jd、1688、guazi、douban、imdb、dictionary |
| 职场 / 招聘 | 51job、boss、linkedin、linkedin-learning、upwork |
| 工具 / 其它 | wikipedia、wikidata、google、duckduckgo、yahoo、producthunt、steam、chess |

查看完整清单：

```powershell
opencli list          # 所有站点与命令
opencli list -f yaml  # YAML 格式
```

已缓存的站点及描述见 `data/sites_metadata.json`。

## 项目结构

```
OpenCliWeb/
├── README.md                 # 中文文档
├── README_en.md              # 英文文档
├── LICENSE                   # MIT 许可证
├── requirements.txt          # Python 依赖
├── pyproject.toml            # ruff 配置
├── .env_sample               # 环境变量样例
├── run_cli.ps1               # 激活虚拟环境（命令行入口）
├── run_webui.ps1             # 激活虚拟环境并启动 WebUI
├── data/                     # 运行时生成：站点描述缓存（不入版本库）
│   └── sites_metadata.json
├── res/                      # 图片资源
│   ├── logo.png
│   ├── webui_0.png / webui.png / webui_1.png
│   └── cat_typing.gif
└── src/
    ├── open_cli.py           # 命令行入口
    ├── open_web.py           # WebUI 入口（NiceGUI）
    ├── services/
    │   └── opencli_service.py # 服务初始化与自检、事件流封装
    ├── opencli/
    │   ├── IntelligentAgent.py # LLM 智能体：工具循环、推理开关
    │   ├── OpenCLITool.py      # 工具实现：site_help / cmd_exec
    │   └── SiteAgent.py        # 站点用途描述自动生成
    ├── ui/
    │   ├── css/app.css
    │   └── js/chat_scroll.js
    └── utils/
        ├── settings.py       # 配置读取与校验
        ├── logger.py         # 日志
        ├── json_extractor.py # JSON 字段安全提取
        └── charstrings.py    # 终端宽度处理
```

## 常见问题

**启动时报 `node.js check failed`**
未安装 Node.js 或不在 `PATH` 中。安装 Node.js ≥ 21.0.0 后重新打开终端。

**启动时报 `opencli check failed`**
OpenCLI 未安装，执行 `npm install -g @jackwener/opencli`，再用 `opencli --version` 确认。

**启动时报 `opencli doctor validation failed`**
`opencli doctor` 的三项检查没有全通过，逐项排查：

- `Daemon: running` —— 本地守护进程未运行。执行任意 opencli 浏览器命令会自动拉起，也可用 `opencli daemon status` 查看。
- `Extension: connected` —— 浏览器扩展未连接。确认 Chrome 已安装并启用 Browser Bridge 扩展。
- `Connectivity: connected` —— 目标站点未连通。确认 Chrome 已登录该网站。
- 提示 `Browser profile "xxx" is not connected` —— 项目会自动尝试 `opencli profile use xxx` 后重试，也可手动执行。

参考 [OpenCLI 故障排查文档](https://opencli.info/docs/guide/troubleshooting.html)（英文）。

**第一次查询很慢**
首次运行需要为每个站点生成一句用途描述（由 LLM 依据站点帮助文档反推），结果写入 `data/sites_metadata.json`。之后只做增量维护，第二次起就很快了。

**站点描述不准 / 想重建缓存**
删除 `data/sites_metadata.json` 后重启即可自动重建；也可以直接编辑其中的 `desc` 字段。

**WebUI 提示「用户名或密码错误」**
确认 `.env` 中已设置 `WEBUI_USERNAME` 与 `WEBUI_PASSWORD`（代码中这两项没有默认值，缺省为 `None`）。

**端口被占用**
修改 `.env` 中的 `PORT`。

**本地模型报 400 / 参数相关错误**
项目为兼容 llama.cpp 系列，在请求体中附带 `enable_thinking`、`reasoning_strength` 等扩展字段。部分 OpenAI 兼容端点不接受这些字段，可尝试从 `src/opencli/IntelligentAgent.py` 的 `extra_body` 中移除。

**PowerShell 提示无法加载 `Activate.ps1`**
执行策略限制。运行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 后重试。

**必须在项目根目录运行吗**
是。项目内部使用相对路径读取 `data/` 与 `src/ui/`，在子目录下运行会找不到站点缓存和静态资源。

**怎么让回答用英文**
把 `.env` 中的 `LANGUAGE` 改为 `English`。

## 视频演示

点击打开 B 站视频：

[![WebUI](https://i2.hdslb.com/bfs/archive/3b9b9e079c254a26c2759f86028e926d5ea981cf.jpg@308w_174h)](https://www.bilibili.com/video/BV1DNG86eEr3)

## 致谢

- [OpenCLI](https://github.com/jackwener/opencli) —— 提供底层的网站适配器与浏览器桥接能力（Apache-2.0 许可）。
- [Llamarkdown](https://github.com/ShionWakanae/Llamarkdown) —— WebUI 界面来源。
- [NiceGUI](https://github.com/zauberzeug/nicegui) —— Web 框架。

作者：

[![CSDN](https://img.shields.io/badge/若苗瞬-CSDN-blue)](https://blog.csdn.net/ddrfan?type=blog)
[![Bilibili](https://img.shields.io/badge/欢迎-bilibili-red?style=flat&logo=youtube)](https://space.bilibili.com/688222797)

## 许可证

[![license](https://img.shields.io/github/license/ShionWakanae/OpenCliWeb.svg "MIT license")](LICENSE)

本项目基于 MIT 许可证开源。你可以在遵守许可证条款的前提下自由使用、修改和分发本项目的代码。

## 参与贡献

欢迎提交 issue 和 pull request。

- 提交前请先阅读[工作原理](#工作原理)一节，理解当前的实现方式。
- 改动后请确认命令行与 WebUI 两条路径都能正常运行。
- 文档改动请同步更新 `README.md` 与 `README_en.md`，保持两版结构一致。
