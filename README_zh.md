# Always Attend (中文说明)

一个自动提交大学每周考勤代码的工具，内置 Okta 多因素认证（MFA）处理功能。

该项目仅用于教育和个人学习，旨在演示自动化技术。请负责任地使用，并遵守您所在机构的政策。

## 主要功能

- **自动提交**：自动登录并提交考勤代码。
- **Okta MFA 支持**：使用 TOTP（身份验证器应用）密钥处理 Okta MFA。
- **持久化会话**：重复使用登录会话，以最大限度地减少 MFA 提示并加快后续运行速度。
- **灵活的代码源**：支持从环境变量、本地 JSON 文件或远程 URL 加载考勤代码。
- **GitHub Actions 集成**：包含一个工作流程，可自动从 GitHub Issues 中获取代码。
- **跨平台**：可在任何支持 Python 和 Playwright 的系统上运行。

## 工作原理

该项目使用 [Playwright](https://playwright.dev/python/) 控制浏览器并模拟用户操作。它由两个主要脚本组成：

1.  `login.py`：一个用于执行初始登录的交互式脚本。它会打开一个浏览器，让您输入凭据和 MFA 代码。成功后，它会将您的会话状态（Cookie 和本地存储）保存到 `storage_state.json` 文件中。
2.  `submit.py`：该脚本使用 `storage_state.json` 中保存的会话，直接访问考勤门户并提交您的代码，无需再次登录。
3.  `main.py`：主入口点，能智能检查是否存在有效会话。如果不存在，它会首先运行登录过程，然后继续提交代码。

## 快速开始

#### 1. 环境要求

- Python 3.8+
- 拥有已启用 Okta MFA 的大学帐户。
- 您的 TOTP 密钥（身份验证器应用中的 Base32 字符串）。

#### 2. 克隆仓库

```bash
git clone https://github.com/tutu/always-attend.git
cd always-attend
```

#### 3. 创建并激活虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows 用户请使用: .venv\Scripts\activate
```

#### 4. 安装依赖

这将安装所需的 Python 包和用于 Playwright 的 Chromium 浏览器。

```bash
pip install -r requirements.txt
playwright install chromium
```

#### 5. 配置您的凭据

复制环境文件示例并填写您的详细信息。

```bash
cp .env.example .env
```

现在，在文本编辑器中打开 `.env` 文件并设置以下内容：
- `USERNAME`：您的大学邮箱地址。
- `PASSWORD`：您的密码。
- `TOTP_SECRET`：用于 MFA 的 Base32 编码的 TOTP 密钥。

#### 6. 运行程序

执行主脚本。首次运行时，它将触发交互式登录过程。

```bash
python main.py
```

按照终端中的提示操作。浏览器窗口将打开，以便您完成登录。保存有效会话后，后续运行将是非交互式的，并直接提交代码。

## 配置选项

可以通过多种方式提供考勤代码，按优先级排序如下：

1.  **环境变量（按课程）**：最高优先级。定义与您的课程时段匹配的变量。
    ```bash
    # .env 文件示例
    "Workshop 1"="CODE123"
    "Applied 2"="CODE456"
    ```

2.  **从 URL 自动发现**：脚本可以构建一个 URL 来获取 JSON 文件。
    - `COURSE_CODE`：例如 "FIT1045"
    - `WEEK_NUMBER`：例如 "4"
    - `CODES_BASE_URL`：托管代码的基础 URL。
    - 脚本将从 `{CODES_BASE_URL}/data/{COURSE_CODE}/{WEEK_NUMBER}.json` 获取。

3.  **直接 URL (`CODES_URL`)**：指向包含代码的 JSON 文件的直接 URL。

4.  **本地文件 (`CODES_FILE`)**：指向本地 JSON 文件的路径。

5.  **内联字符串 (`CODES`)**：用分号分隔的 `slot:code` 对字符串。

**JSON 文件格式示例:**
```json
[
  {"date": "2025-08-18", "slot": "Workshop 1", "code": "JZXBA"},
  {"date": "2025-08-19", "slot": "Workshop 2", "code": "AJYV7"}
]
```

## 使用方法

虽然 `main.py` 是主要入口点，但您也可以使用单个脚本来执行特定任务。

#### `main.py` (推荐)
主脚本智能地处理登录和提交。
```bash
# 运行完整流程：检查会话，如果需要则登录，然后提交
python main.py

# 强制浏览器可见
python main.py --headed

# 以“演习”模式运行，查看将要提交的代码（不会实际提交）
python main.py --dry-run
```

#### `login.py`
用于手动刷新您的会话状态。
```bash
# 运行交互式登录以创建/更新 storage_state.json
python login.py --headed

# 检查当前会话是否仍然有效
python login.py --check-only
```

#### `submit.py`
当您确定 `storage_state.json` 有效时，用此脚本提交代码。
```bash
# 使用现有会话提交代码
python submit.py

# 查看将要提交的代码，但不会实际提交
python submit.py --dry-run
```

## GitHub Actions 集成

该仓库包含一个工作流程 (`.github/workflows/attendance-from-issues.yml`)，可自动从新创建的 GitHub Issues 中提取考勤代码。

- **工作原理**：当创建带有“Attendance Codes”模板的 Issue 时，工作流程会运行，解析 Issue 正文，并将代码保存到仓库内的 JSON 文件中（例如 `data/FIT1045/4.json`）。
- **使用方法**：您可以将 `CODES_BASE_URL` 配置为指向您仓库的原始内容 URL (`https://raw.githubusercontent.com/<your-username>/<your-repo>/main`)，以自动拉取最新的代码。这种设置使您只需通过创建 GitHub Issue 即可更新代码，而无需接触环境变量。
