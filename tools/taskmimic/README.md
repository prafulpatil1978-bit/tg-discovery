# taskmimic

**Show your computer a task once, then let an AI repeat it.**

taskmimic watches you do a task on screen, turns what it saw into a reusable step-by-step skill with
Gemini or a GitHub Copilot model, and replays that skill with autonomous computer use. It works for tasks
like reviewing and commenting, filling forms, or any sequence of clicks and typing.

It is one Python file with four small dependencies. Nothing is recorded until you start it, and nothing
leaves your computer until you run `learn` or `run`.

```
record  ──►  learn  ──►  run
(you do it)  (AI writes the skill)  (AI does it, you watch / approve)
```

## Install (1 minute)

```bash
pip install -r requirements.txt        # or: pipx install ./tools/taskmimic  (gives a `taskmimic` command)
python taskmimic.py doctor             # checks screen capture, mouse/keyboard access and your API key
```

Pick **one** model provider:

| Provider | Set | Default model |
|---|---|---|
| Gemini | `GEMINI_API_KEY` ([get one](https://aistudio.google.com/apikey)) | `gemini-3.6-flash` |
| GitHub Copilot models (GitHub Models) | `GITHUB_TOKEN` (fine-grained PAT with **models: read**) | `openai/gpt-4.1` |
| OpenAI or any OpenAI-compatible API (Azure, LM Studio…) | `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) | `gpt-4.1` |
| Ollama (fully local, private) | nothing; `--provider ollama` | `qwen2.5vl:7b` |

Override the model with `--model` or `TASKMIMIC_MODEL`. The model must accept images.

**Permissions:**
- **macOS:** allow your terminal under System Settings › Privacy & Security › *Accessibility*,
  *Input Monitoring* and *Screen Recording*.
- **Linux:** needs an X11 session. Wayland blocks global input capture.
- **Windows:** works out of the box. To automate apps running as admin, use an admin terminal.

## Use

```bash
# 1. Record: do the task once at a normal pace. Stop with Ctrl+Alt+S (or Ctrl+C in the terminal).
python taskmimic.py record review-pr

# 2. Learn: the model turns the recording into a skill (SKILL.md + skill.json).
python taskmimic.py learn review-pr --hint "review the open PR and leave a comment"

# 3. Run: the AI repeats it, asking before every action.
python taskmimic.py run review-pr --input pr_url="https://github.com/org/repo/pull/42"
python taskmimic.py run review-pr --auto ...        # unattended
```

Other commands: `list`, `show NAME`, `export NAME DIR`, `doctor`. Add `--help` to any command.

### Tips for good skills
- Record one clean run. Typos and stray clicks are fine; the model filters them out.
- Values that change next time (names, links, text) become **inputs** you pass with `--input`.
- Record the task 2–3 times with different data, then run `learn NAME --all` for a more general skill.
- Before a run, read `~/.taskmimic/skills/NAME/SKILL.md`. Edit `skill.json` by hand if you want; it is
  validated when you run it.
- For review and comment tasks, the model writes the comment itself in `review` steps. Its findings also
  go to `runs/<time>/report.md`.

## Safety and privacy

| | |
|---|---|
| Manual only | Recording starts only with `record` and stops with **Ctrl+Alt+S** or after 30 min (`--max-minutes`). |
| Passwords | Press **Ctrl+Alt+P** to pause while you type secrets, or use `record --no-text` to keep only the length of typed text. Skills are told never to contain passwords. |
| Approval | `run` asks before **every** action: Enter = do, `s` = skip, `t` = edit text, `q` = quit. `--dry-run` plans without touching anything. |
| Risky shortcuts | Shortcuts that close windows or sign you out (Alt+F4, Ctrl+W, Cmd+Q, Win+L…) are always confirmed, even with `--auto`, unless you pass `--allow-risky`. |
| Kill switch | **Ctrl+Alt+S**, push the mouse into any screen corner, or press Ctrl+C. |
| Validation | Every model action is checked (allowed type, coordinates on screen, known keys). After 3 invalid answers in a row the run stops. |
| Prompt injection | The agent is told that text on screen is data, not instructions. Approval mode is your backstop; use `--auto` only for screens you trust. |
| Data | Everything stays in `~/.taskmimic` (`TASKMIMIC_HOME`). Screenshots go to your chosen provider only during `learn` and `run`. Use Ollama to keep everything local. |
| Audit | Each run keeps `log.jsonl`, the screenshots it acted on, and `report.md`. |

## How it works

- **record:** `pynput` listens to clicks, scrolls and keys. Typing is merged into text, shortcuts are
  detected, double clicks are merged. A screenshot (`mss`) is taken at each action and whenever the
  screen changes, downscaled to 1280 px wide JPEG. Coordinates are normalised to 0–1000, so skills
  survive different resolutions and HiDPI screens.
- **learn:** sends the action timeline plus up to 20 screenshots (clicks marked with a red ring) and asks
  for a JSON skill: each step has an intent, a visible target ("the blue Submit button"), an action and
  an expected result. Invalid drafts are sent back once with the errors.
- **run:** a loop of *screenshot → model picks the next action → validate → (approve) → execute*,
  until the model reports `done` or `fail`, or the action limit is reached.

## Use it from Copilot or Gemini agents

- `export NAME DIR` writes `SKILL.md` + `skill.json` + `taskmimic.py` into a folder, for example
  `.github/skills/` for GitHub Copilot, or a Gemini CLI skills/extension folder. `SKILL.md` uses the Agent
  Skills format (YAML `name`/`description` front matter), so agents that read skills know when to use it
  and how to run it.
- [`SKILL.md`](SKILL.md) in this folder teaches an agent to use taskmimic itself (record, learn, run).

## Configuration

| Env var | Default | |
|---|---|---|
| `TASKMIMIC_HOME` | `~/.taskmimic` | data folder |
| `TASKMIMIC_PROVIDER` | auto (first key found: Gemini, GitHub, OpenAI) | `gemini`, `github`/`copilot`, `openai`, `ollama` |
| `TASKMIMIC_MODEL` | per provider | |
| `TASKMIMIC_STOP_HOTKEY` / `TASKMIMIC_PAUSE_HOTKEY` | `<ctrl>+<alt>+s` / `<ctrl>+<alt>+p` | pynput hotkey syntax |
| `TASKMIMIC_MAX_WIDTH` | `1280` | screenshot width |
| `TASKMIMIC_DEBUG` | off | `1` logs raw key events (not when `--no-text`) |

## Limits

- One screen region (all monitors as one image). Very large multi-monitor setups lose detail when
  downscaled; raise `TASKMIMIC_MAX_WIDTH` if needed.
- Linux needs X11; Wayland is not supported.
- How well `run` works depends on the model. Start in approval mode and switch to `--auto` once a skill
  is reliable.

## Tests

```bash
pip install pytest && python -m pytest tests     # unit tests, no display or network needed
```

The recorder, learner and runner were also tested end to end on a virtual X display. The test recorded
real input into a Chromium form, learned a skill, then let the agent post into the form. It also covered
the corner failsafe, rejection of invalid actions, dry run and approval mode.
