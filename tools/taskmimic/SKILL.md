---
name: taskmimic
description: "Learn a repetitive computer task by watching the user do it once, then repeat it with autonomous computer use. Use when the user wants to automate clicking, typing, reviewing or commenting in desktop apps or websites that have no API."
---

# taskmimic

`taskmimic.py` (next to this file) records the user doing a task, turns the recording into a skill with a
vision model (Gemini, GitHub Copilot models, OpenAI or local Ollama), and replays it by controlling the
mouse and keyboard.

## When to use
- The user says "watch me do this", "learn this task", "automate these clicks", or "do what I did yesterday
  again".
- The task happens in a GUI (desktop app or website) and no API or CLI is available. If one exists, use it
  instead.

## Workflow
1. Check setup: `python taskmimic.py doctor`. If anything shows ✗, relay the fix it prints, such as
   macOS permissions or a missing API key.
2. Record (the user must do this themselves): tell them to run
   `python taskmimic.py record <name>`, do the task once, then press **Ctrl+Alt+S**. They should press
   **Ctrl+Alt+P** around any password entry.
3. Learn: `python taskmimic.py learn <name> --hint "<one sentence goal>"`. Then read
   `~/.taskmimic/skills/<name>/SKILL.md` and summarise the steps and inputs for the user.
4. Run: `python taskmimic.py run <name> --input key=value ...`. It runs in approval mode by default, so the
   user approves each action in the terminal. Add `--auto` only when the user explicitly asks for
   unattended runs. Use `--dry-run` to preview.
5. Report: the result is in the exit code (0 done, 2 failed or stopped by the agent, 3 aborted by the
   user). Notes and the action log are in the printed `runs/<time>/report.md`.

## Rules
- Never start a recording without the user asking. It captures their screen and keystrokes.
- Never pass passwords as `--input`. If a skill needs a login, ask the user to sign in first.
- Do not add `--allow-risky` unless the user asks for it by name.
- Commands: `record`, `learn`, `run`, `list`, `show <name>`, `export <name> <dir>`, `doctor`.
