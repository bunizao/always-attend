# Cold Start Bootstrap

Do not assume the machine is ready.
Bootstrap in this exact order before the first real `attend` command.

## 1. Confirm Python exists

Run one of these:

```bash
python3 --version
python --version
```

If neither command works, stop and report that Python 3.11+ is required before Always Attend can run.

## 2. Confirm `uv` exists

Run:

```bash
uv --version
```

If `uv` is missing, install it with the Python interpreter that worked in step 1:

```bash
python3 -m pip install uv
```

If only `python` exists, use:

```bash
python -m pip install uv
```

## 3. Confirm Always Attend exists

Try the CLI first:

```bash
attend doctor --json
```

If `attend: command not found`, install the tool:

```bash
uv tool install always-attend
```

Then run:

```bash
attend doctor --json
```

If the tool was installed but the shell still cannot find `attend`, use this fallback command prefix:

```bash
uv tool run --from always-attend attend
```

Example:

```bash
uv tool run --from always-attend attend doctor --json
```

If you are inside the Always Attend repository, `PYTHONPATH=src python -m always_attend ...` is also valid for local development.

## 4. Read `doctor --json`

Use `attend doctor --json` as the machine-readable gate before collecting or submitting anything.

If `doctor --json` returns an `install_hint`, prefer that exact command.

The expected setup sequence after Always Attend is available is:

1. `attend doctor --json`
2. Install missing source CLIs such as `okta`, `moodle-cli`, and `edstem`
3. `playwright install chromium`
4. `attend auth login <attendance-url> --json`

`attend auth login` requires a human to complete the interactive login flow.

## Dependency Recovery Rules

When `doctor --json` reports missing tools, fix them before moving on.

- `okta`: `uv tool install okta-auth-cli`
- `moodle-cli`: `uv tool install moodle-cli`
- `edstem`: `uv tool install edstem-cli`
- `playwright` browser runtime: `playwright install chromium`

Do not skip a missing dependency and continue with weaker behavior.
If a dependency cannot be installed, stop and report it clearly.

Do not block on OCR. Image links are meant for the model to inspect directly.
