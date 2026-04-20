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
  An attendance CLI built for agents.<br>
  Always-Attend inspects what is open, collects evidence, matches candidates, and submits only when it is confident.
</p>

[Python](https://www.python.org)
[uv](https://github.com/astral-sh/uv)
[AI Native](#philosophy)

Always-Attend does what most people do manually: find the code, figure out which slot it belongs to, and submit it. It checks what's actually open, pulls candidates from Gmail, Moodle, Ed, and GOG, and submits only when it's confident.

It's built to be run by an **agent**. The external sources are eyes, and `attend` is the hand. **The agent is the one that decides.**

## Philosophy

Always-Attend checks before it acts, looking at what's actually open, then gathering evidence from multiple sources before making a move.

This makes it composable with AI agents in a way that scripts rarely are. An agent can inspect, reason, and decide, or hand off entirely and let Always-Attend run the loop. Either way, the result comes back as structured JSON, so the agent knows exactly what happened and what's left.

## For Agents

Copy this prompt and give it to your agent:

```text
Bootstrap always-attend on this machine.

Read and follow:
https://raw.githubusercontent.com/bunizao/always-attend/main/skills/BOOTSTRAP.md

Resolve any issues you encounter autonomously before moving to the next step.
```

## Quick Start

```bash
uv tool install always-attend
attend setup
```

## What It Does

- Inspect the attendance site DOM before guessing from external sources
- Collect structured code candidates from Gmail, Moodle, Ed, and GOG
- Package text and image evidence for multimodal reasoning
- Submit guarded high-confidence matches
- Report rejected, locked, and unresolved items in JSON

---

## Story

> *The following is excerpted from a reflection I wrote in my FIT1045 H3 report.*

I've been developing Always-Attend for two months now. There are already more than 150 commits, and the project has grown from a small 500-line script into something I'm genuinely proud of. Today it has over 30 Python files and around 6,000 lines of code. Modern, elegant, and useful, something I believe many people would enjoy.

Along the way, AI helped me move faster. Codex and Claude Code set up test frameworks, caught bugs, and iterated alongside me. But the thinking was always mine, the architecture, the decisions, the refactoring over details no one would ever notice.

Then ChatGPT Atlas launched. I watched it find the attendance code in Gmail, open a GitHub issue, and fill the form, all on its own. For a moment, I thought: *Always-Attend doesn't matter anymore.* It felt like every startup story I'd heard, quietly replaced by something shinier and better-funded.

I kept building anyway. Not to compete, but to finish what I started.

Somewhere in that process, the project stopped being just a tool. It became a record of how I think, my curiosity, my patience, and the slow satisfaction of watching something come alive line by line.

---

That was then. Now, Always-Attend is leaning into what once felt like a threat. The next chapter is agentic, less scripting, more thinking. Less automation, more autonomy. The tool that once felt obsolete is still figuring out what it wants to be when it grows up.

---

## License

[GPL-3.0](LICENSE)
