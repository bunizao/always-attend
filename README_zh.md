<h1 align="center">Always Attend</h1>
<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg">
  <img src="https://img.shields.io/badge/License-GPLv3-blue.svg">
  <img src="https://img.shields.io/github/last-commit/bunizao/always-attend">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey">
  <p align="center">  
  <img src="https://img.shields.io/badge/status-Public%20Beta-orange?style=for-the-badge">
<p align="center">
  一个帮助你解放双手，自动化提交每周考勤代码的工具，当前为 Public Beta。<br>
  ⚠️ <b>请合理合规使用，并遵守学校与网站的使用条款。</b>
</p>

<p align="center">
  <a href="README.md"><b>English README</b></a>
</p>

> [!WARNING]  
> 本项目当前处于 **Public Beta**。功能可能变更且可能存在缺陷。     
> 提交反馈： [![Open Issue](https://img.shields.io/badge/Open-Issue-blue)](https://github.com/bunizao/always-attend/issues/new)   

#### 此文档由 [**ChatGPT 5**](https://chatgpt.com) 翻译，原始内容用英语编写，仅供参考。 

## 📥 如何下载本项目

任选一种方式把项目文件夹下载到电脑：

### 方式一：使用 Git（推荐）
- 安装 Git：https://git-scm.com/downloads
- macOS / Linux（终端）：
```bash
git clone https://github.com/bunizao/always-attend.git
cd always-attend
```
- Windows（PowerShell 或 命令提示符）：
```bat
git clone https://github.com/bunizao/always-attend.git
cd always-attend
```

### 方式二：下载 ZIP（不需要 Git）
- 打开项目主页：https://github.com/bunizao/always-attend
- 点击绿色的“Code”按钮 → “Download ZIP”
- 或者直接下载 ZIP 链接：https://github.com/bunizao/always-attend/archive/refs/heads/main.zip
- 解压 ZIP：
  - Windows：右键 ZIP → “全部解压...”
  - macOS：双击 ZIP 自动解压
- 打开解压后的 `always-attend` 文件夹

### 下载完成后如何运行
- macOS：双击 `Always-Attend.command`
- Windows：双击 `Always-Attend.bat`，或右键 `Always-Attend.ps1` → 以 PowerShell 运行
- 首次运行会自动进入引导设置

## 🚀 一键启动（推荐）

双击即可运行，包含首次引导设置：

- macOS：双击 `Always-Attend.command`
- Windows：双击 `Always-Attend.bat`（或运行 `Always-Attend.ps1`）

启动器会做什么：
- 检查系统中的 Python（以及可选的 Git）
- 首次运行创建并激活虚拟环境并安装依赖
- 运行首次设置向导（门户 URL、账号、周次、浏览器）
- 从 `data/*/*.json` 自动检测最新周并设置 `WEEK_NUMBER`
  - 若希望每次运行都提示周次，设置 `WEEK_PROMPT=1`
- 简化执行：直接调用 `python main.py`，无复杂菜单

首次设置功能：
- ASCII 艺术横幅
- 首次运行显示隐私政策并征得同意
- 学校快速配置（包含 Monash Malaysia 选项）
- 邮箱与密码输入
- 周次配置

注意：
- Git 可选；未安装将跳过更新步骤
- 需要已安装 Chrome/Edge（默认使用系统浏览器）

快速开始：
```bash
# macOS：双击 Always-Attend.command
# Windows：双击 Always-Attend.bat

# 或直接运行
python main.py
```
更多运行细节与可选参数见下方“快速开始（Quick Start）”章节。

## 前置条件

- Python 3.11 或更高版本
- 已安装 Google Chrome 或 Microsoft Edge 浏览器

## 安装

0) 安装 Git
- 从 https://git-scm.com/downloads 下载并安装

1) 克隆并进入项目
```bash
git clone https://github.com/bunizao/always-attend.git
cd always-attend
```

2) 创建并激活虚拟环境
- macOS / Linux：
```bash
python -m venv .venv
source .venv/bin/activate
```
- Windows（PowerShell）：
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
若提示“已禁止运行脚本”，可执行：
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
然后再次运行 `.venv\Scripts\Activate.ps1`。若 PowerShell 仍报错，可右键以管理员身份运行 PowerShell 后重试 `Activate.ps1`。

3) 安装依赖
```bash
pip install -U pip
pip install -r requirements.txt
```

4) 设置环境变量
```bash
cp .env.example .env
```
使用任意编辑器修改 `.env`，快速示例（VS Code）：
```bash
code .env
```

重要提示：
- Monash University Malaysia 用户：将 `PORTAL_URL` 设置为 `https://attendance.monash.edu.my`
- 请务必包含 `https://` 前缀
> [!IMPORTANT]
> 本项目**未获蒙纳士大学资助、附属或认可**。
> 
> 这是一个独立项目，与蒙纳士大学没有任何官方联系。  

也可直接在终端中更新 `PORTAL_URL`：
```bash
# macOS
sed -i '' 's/^PORTAL_URL=.*/PORTAL_URL="https:\/\/your.portal.url"/' .env
# Linux
sed -i 's/^PORTAL_URL=.*/PORTAL_URL="https:\/\/your.portal.url"/' .env
```

5) 快速开始（Quick Start）
```bash
python main.py
```
运行后会发生什么：
- 从 `.env` 和当前环境读取配置（确保设置 `PORTAL_URL`，考勤代码存放于 `data/` 或 `CODES_DB_PATH` 指定目录）。
- 若未找到有效会话，将自动弹出浏览器进行单点登录 (SSO)，并显示 MFA 验证页面；完成验证后会将会话保存到 `storage_state.json`。
- 脚本会进入考勤门户，扫描本周条目并提交代码。
- 请在终端查看日志结果；若缺少代码（常见情况），可使用项目的 Issue 模板提交：[![Open Issue](https://img.shields.io/badge/Open-Issue-blue)](https://github.com/bunizao/always-attend/issues/new)
- 可选参数：`--headed` 观察浏览器、`--dry-run` 仅预览不提交、`--week N` 指定周次。

## 📦 考勤数据库

工具只会从 `data/`（或 `CODES_DB_PATH` 指定目录）加载考勤代码。目录推荐维持如下结构：

```
data/
  FIT1045/
    3.json     # [{ "slot": "Workshop 01", "code": "LCPPH" }, ...]
  FIT1047/
    7.json
```

若你维护了单独的 Git 仓库，可通过环境变量自动同步：

```bash
export CODES_DB_REPO="git@github.com:you/attendance-db.git"
export CODES_DB_BRANCH="main"
```

每次运行时，程序都会克隆或 `git pull` 该仓库，确保本地数据始终最新。

6) 更新项目
```bash
git pull
```

### 本地模拟门户（JSON）
- 启动：`PYTHONPATH=src python -m mock_portal.server --port 8000`
- 数据：`data/mock_units.json`（包含 `#22_Oct_25`、`#23_Oct_25` 两天）
- 运行：设置 `PORTAL_URL=http://127.0.0.1:8000/student/Units.aspx`（可加 `HEADLESS=0` 观察浏览器）
- 重载：`POST /mock/reset` 会重新加载 JSON（无需数据库）
- 详见 `docs/mock_portal.md`，包含 Always Works™ 验证流程

---

完整环境变量列表见下文（Environment Variables）。

## 故障排查（Troubleshooting）

- 如果每次都要求 MFA：请再次执行有头登录以刷新 `storage_state.json`
- 如果浏览器无法启动：确认已安装 Chrome 或 Edge，或设置 `BROWSER_CHANNEL=chrome/msedge`
- Windows 若激活脚本失败：以管理员身份打开 PowerShell，再运行 `.venv\Scripts\Activate.ps1`
- 运行时请勿使用 VPN，这可能导致 Okta 拒绝连接。
## 常见问题（Windows）

- **`python` 与 `py`**：在部分 Windows 环境中 `python` 命令不可用或指向其它版本，可使用 `py` 代替，如 `py -m venv .venv`、`py main.py`。
- **切换 Git Bash 与 PowerShell**：在 VS Code 等终端的下拉菜单中可选择 "Git Bash" 或 "PowerShell"；某些命令（如 `source`）仅在 Git Bash 可用，而 PowerShell 使用 `.\` 调用脚本。
- **路径转义问题**：PowerShell 使用反斜杠（`\`），可能被视为转义字符；请使用引号或双反斜杠，如 `C:\path\to\file`。Git Bash 则使用正斜杠（`/`）。

## 命令行参数（Command-Line Arguments）

main.py

| 参数 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| `--browser` | string | 浏览器内核（`chromium`/`firefox`/`webkit`） | `--browser chromium` |
| `--channel` | string | 系统浏览器通道 | `--channel chrome` |
| `--headed` | flag | 显示浏览器界面（等价于 `HEADLESS=0`） | `--headed` |
| `--dry-run` | flag | 仅解析并打印代码，不提交 | `--dry-run` |
| `--week` | int | 提交第 N 周的代码 | `--week 4` |
| `--login-only` | flag | 仅执行登录/刷新会话后退出 | `--login-only` |

login.py

| 参数 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| `--portal` | string URL | 考勤门户地址（覆盖 `PORTAL_URL`） | `--portal https://attendance.example.edu/student/Default.aspx` |
| `--browser` | string | 浏览器内核（`chromium`/`firefox`/`webkit`） | `--browser chromium` |
| `--channel` | string | 系统浏览器通道 | `--channel chrome-beta` |
| `--headed` | flag | 显示浏览器界面（首次登录推荐） | `--headed` |
| `--storage-state` | string path | `storage_state.json` 保存路径 | `--storage-state storage_state.json` |
| `--user-data-dir` | string path | 持久化浏览器用户数据目录 | `--user-data-dir ~/.always-attend-profile` |
| `--check` | flag | 保存后再次打开门户验证登录 | `--check` |
| `--check-only` | flag | 仅验证当前会话，不打开登录 | `--check-only` |

submit.py

| 参数 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| `--browser` | string | 浏览器内核（`chromium`/`firefox`/`webkit`） | `--browser chromium` |
| `--channel` | string | 系统浏览器通道 | `--channel msedge` |
| `--headed` | flag | 显示浏览器界面 | `--headed` |
| `--dry-run` | flag | 仅解析并打印代码，不提交 | `--dry-run` |
| `--week` | int | 提交第 N 周的代码 | `--week 6` |
| `--debug` | flag | 输出调试级日志 | `--debug` |
| `--verbose` | flag | 更详细的日志（等同 `--debug`） | `--verbose` |
| `--skip-update` | flag | 跳过运行前的 git 更新检查 | `--skip-update` |

## 环境变量（Environment Variables）

| 变量 | 类型 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- | --- |
| `PORTAL_URL` | string URL | 是 | 考勤门户基础地址 | `https://attendance.monash.edu.my` |
| `CODES_DB_PATH` | string path | 否 | `课程/周次.json` 根目录 | `/srv/attendance-data` |
| `CODES_DB_REPO` | string URL | 否 | 同步到本地的 Git 仓库地址 | `git@github.com:you/attendance-db.git` |
| `CODES_DB_BRANCH` | string | 否 | 同步使用的分支 | `main` |
| `WEEK_NUMBER` | int | 否 | 指定周次（否则自动检测最新周） | `4` |
| `USERNAME` | string | 否 | Okta 用户名（自动登录） | `student@example.edu` |
| `PASSWORD` | string | 否 | Okta 密码（自动登录） | `correcthorsebattery` |
| `TOTP_SECRET` | string（base32） | 否 | MFA TOTP 秘钥（自动登录） | `JBSWY3DPEHPK3PXP` |
| `AUTO_LOGIN` | flag（0/1） | 否 | 是否开启自动登录 | `1` |
| `BROWSER` | string | 否 | 内核覆盖（`chromium`/`firefox`/`webkit`） | `chromium` |
| `BROWSER_CHANNEL` | string | 否 | 系统通道（`chrome`/`msedge` 等） | `chrome` |
| `HEADLESS` | flag（0/1 或 true/false） | 否 | 无界面运行（0 表示关闭） | `0` |
| `USER_DATA_DIR` | string path | 否 | 持久化浏览器上下文目录 | `~/.always-attend-profile` |
| `LOG_PROFILE` | string | 否 | 日志模式（`user`/`quiet`/`debug`/`verbose`） | `verbose` |
| `LOG_FILE` | string path | 否 | 可选日志文件路径 | `/tmp/always-attend.log` |
| `SKIP_UPDATE_CHECK` | flag（0/1 或 true/false） | 否 | 设置为 1 时跳过运行前的 git 更新 | `1` |

## 免责声明（Disclaimer）

- 本项目仅用于学习与个人用途。请合理使用，并遵守学校政策与网站使用条款。
- 本项目与任何高校或服务提供方无隶属、背书或赞助关系。所有名称、标识与商标归其各自所有者。
- 您需对使用本工具及产生的后果自行负责。作者不保证其在您的环境下必然可用。

## 许可证（License）

- 本项目以 GNU General Public License v3.0（GPL‑3.0）授权，完整协议见仓库内 `LICENSE` 文件。
- 您可在 GPL‑3.0 条款下复制、修改和分发本软件；本软件按“现状”提供，不附带任何形式的保证。
