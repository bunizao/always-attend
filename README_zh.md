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

## 📥 获取 Always Attend

公开安装方式只保留两种：

### 方式一：`uv tool`（推荐）
1. 若尚未安装 [uv](https://docs.astral.sh/uv/)，先执行：
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. 安装 `always-attend`，并同时暴露 `playwright` 可执行文件：
   ```bash
   uv tool install --with-executables-from playwright always-attend
   ```
3. 验证 CLI：
   ```bash
   attend --help
   ```

程序会优先使用你本机已安装的 Chrome/Edge；如果确实需要 Playwright 自带的 Chromium 且本机缺失，首次运行时会自动下载。

如果安装后终端里还找不到 `attend`，执行：

```bash
uv tool update-shell
```

### 方式二：`pipx`
1. 若尚未安装 [pipx](https://pipx.pypa.io/stable/installation/)，先执行：
   ```bash
   python3 -m pip install --user pipx
   python3 -m pipx ensurepath
   ```
2. 安装 `always-attend`：
   ```bash
   pipx install always-attend
   ```
3. 暴露注入包里的 `playwright` 可执行文件：
   ```bash
   pipx inject --include-apps always-attend playwright
   ```
4. 验证 CLI：
   ```bash
   attend --help
   ```

## 🚀 运行 CLI

公开命令入口：

- `attend`

## 前置条件

- Python 3.11 或更高版本
- 已安装 Google Chrome 或 Microsoft Edge 浏览器

## 安装与首次运行

先用上面的 `uv tool` 或 `pipx` 完成安装，再运行：

```bash
attend

# 查看可集成的运行时路径
attend paths --json
```

安装完成后，可在用户配置目录中设置 `.env`。Monash University Malaysia 用户请将 `PORTAL_URL` 设为 `https://attendance.monash.edu.my`，并保留 `https://` 前缀。

> [!IMPORTANT]
> 本项目**未获蒙纳士大学资助、附属或认可**。
>
> 这是一个独立项目，与蒙纳士大学没有任何官方联系。

运行时文件现在默认放到标准用户目录：
- Linux：
  `~/.config/always-attend/.env`、
  `~/.local/state/always-attend/`、
  `~/.local/share/always-attend/codes/`
- macOS：
  `~/Library/Application Support/always-attend/config/.env`、
  `~/Library/Application Support/always-attend/state/`、
  `~/Library/Application Support/always-attend/data/codes/`
- Windows：
  `%APPDATA%\\always-attend\\config\\.env`、
  `%LOCALAPPDATA%\\always-attend\\state\\`、
  `%LOCALAPPDATA%\\always-attend\\data\\codes\\`
- 如需覆盖，可使用 `ENV_FILE`、`STORAGE_STATE`、`ATTENDANCE_STATS_FILE`、`CODES_DB_PATH` 等环境变量

集成契约：
- CLI：`attend paths --json`
- Python：`from always_attend import get_runtime_paths_dict`

## 🧰 CLI 安装细节

### 方案 A —— `uv tool`（推荐）
- 最适合把 `attend` 当作独立 CLI 安装到当前用户环境。
- 安装快，且不会污染你的项目虚拟环境。

```bash
uv tool install --with-executables-from playwright always-attend
attend --dry-run
```

如果运行时需要 Chromium 而本机尚未安装，程序会自动下载。

后续升级：

```bash
uv tool upgrade always-attend
```

### 方案 B —— `pipx`
- 适合已经用 `pipx` 管理 Python CLI 的环境。
- `always-attend` 会被隔离安装在单独的应用环境中。

```bash
pipx install always-attend
pipx inject --include-apps always-attend playwright
attend --dry-run
```

后续升级：

```bash
pipx upgrade always-attend
```

运行后会发生什么：
- 从 `.env` 和当前环境读取配置（确保设置 `PORTAL_URL`，考勤代码存放于 `data/` 或 `CODES_DB_PATH` 指定目录）。
- 若未找到有效会话，将自动弹出浏览器进行单点登录 (SSO)，并显示 MFA 验证页面；完成验证后会将会话保存到用户状态目录中的会话文件。
- 脚本会进入考勤门户，扫描本周条目并提交代码。
- 请在终端查看日志结果；若缺少代码（常见情况），可使用项目的 Issue 模板提交：[![Open Issue](https://img.shields.io/badge/Open-Issue-blue)](https://github.com/bunizao/always-attend/issues/new)
- 可选参数：`--headed` 观察浏览器、`--dry-run` 仅预览不提交、`--week N` 指定周次。

## 📦 考勤数据库

工具只会从 `codes_db_path`（默认是应用数据目录下独立的 `codes/` 目录，或 `CODES_DB_PATH` 指定目录）加载考勤代码。目录推荐维持如下结构：

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

---

完整环境变量列表见下文（Environment Variables）。

## 故障排查（Troubleshooting）

- 如果每次都要求 MFA：请再次执行有头登录以刷新本地会话文件
- 如果浏览器无法启动：确认已安装 Chrome 或 Edge，或设置 `BROWSER_CHANNEL=chrome/msedge`
- 如果安装后找不到 `attend`：重开终端，再执行 `uv tool update-shell` 或 `python3 -m pipx ensurepath`
- 运行时请勿使用 VPN，这可能导致 Okta 拒绝连接。
## 常见问题（Windows）

- **`python` 与 `py`**：在部分 Windows 环境中 `python` 命令不可用或指向其它版本，可使用 `py` 执行引导命令，例如 `py -m pip install --user pipx`。
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
| `--storage-state` | string path | 会话文件保存路径 | `--storage-state /tmp/storage_state.json` |
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
| `SUBMIT_CONCURRENCY` | int | 否 | 同时处理的课程数量上限 | `2` |
| `SUBMIT_TARGET_CONCURRENCY` | int | 否 | 单课程内并行提交任务数 | `3` |
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
