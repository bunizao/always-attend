# Always-Attend

Always-Attend is an AI-native CLI for attendance workflows.
It can inspect the attendance portal, collect evidence from Gmail, Moodle, Ed, and GOG, match likely codes against open items, submit high-confidence results, and report unresolved states in machine-readable JSON.

## Quick Start For Agents

```bash
uv tool install always-attend
attend setup
```

That is the intended bootstrap path for agents.

## What It Does

- Inspect the attendance site DOM before guessing from external sources
- Collect structured code candidates from Gmail, Moodle, Ed, and GOG
- Package text and image evidence for multimodal reasoning
- Submit guarded high-confidence matches
- Report rejected, locked, and unresolved items in JSON

---

# Always-Attend

> *The following is excerpted from a reflection I wrote in my FIT1045 H3 report.*

---

I've been developing Always-Attend for two months now. There are already more than 150 commits, and the project has grown from a small 500-line script into something I'm genuinely proud of. Today it has over 30 Python files and around 6,000 lines of code. Modern, elegant, and useful — something I believe many people would enjoy.

Along the way, AI helped me move faster. Codex and Claude Code set up test frameworks, caught bugs, and iterated alongside me. But the thinking was always mine — the architecture, the decisions, the refactoring over details no one would ever notice.

Then ChatGPT Atlas launched. I watched it find the attendance code in Gmail, open a GitHub issue, and fill the form — all on its own. For a moment, I thought: *Always-Attend doesn't matter anymore.* It felt like every startup story I'd heard, quietly replaced by something shinier and better-funded.

I kept building anyway. Not to compete, but to finish what I started.

Somewhere in that process, the project stopped being just a tool. It became a record of how I think — my curiosity, my patience, and the slow satisfaction of watching something come alive line by line.

---

That was then. Now, Always-Attend is leaning into what once felt like a threat. The next chapter is agentic — less scripting, more thinking. Less automation, more autonomy. The tool that once felt obsolete is still figuring out what it wants to be when it grows up.

---

> *This project is a work in progress. Contributions and feedback are welcome.*
