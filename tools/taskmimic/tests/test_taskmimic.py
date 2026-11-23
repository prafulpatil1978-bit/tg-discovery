"""Unit tests: no display, no network (a local mock server stands in for Gemini / OpenAI-compatible APIs)."""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import taskmimic as tm  # noqa: E402


# ----------------------------------------------------------------- helpers

class FakeKey:
    def __init__(self, char=None, name=None, vk=None):
        self.char, self.name, self.vk = char, name, vk


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "HOME", tmp_path)
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY",
              "TASKMIMIC_PROVIDER", "TASKMIMIC_MODEL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


class Mock:
    """Scripted HTTP server. `replies` is a list of (status, json body, headers) consumed in order."""

    def __init__(self):
        self.requests, self.replies = [], []
        mock = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                mock.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, data, hdrs = mock.replies.pop(0) if mock.replies else (500, {"error": "no reply"}, {})
                raw = json.dumps(data).encode()
                self.send_response(status)
                for k, v in hdrs.items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def gemini(self, obj, status=200, headers=None):
        text = obj if isinstance(obj, str) else json.dumps(obj)
        self.replies.append((status, {"candidates": [{"content": {"parts": [
            {"text": "thinking...", "thought": True}, {"text": text}]}}]}, headers or {}))

    def openai(self, obj, status=200, headers=None):
        text = obj if isinstance(obj, str) else json.dumps(obj)
        self.replies.append((status, {"choices": [{"message": {"content": text}}]}, headers or {}))

    def error(self, status, msg, headers=None):
        self.replies.append((status, {"error": {"message": msg}}, headers or {}))


@pytest.fixture
def mock(monkeypatch):
    m = Mock()
    monkeypatch.setenv("TASKMIMIC_GEMINI_BASE", m.url)
    monkeypatch.setenv("OPENAI_BASE_URL", m.url)
    monkeypatch.setenv("TASKMIMIC_GITHUB_BASE", m.url)
    monkeypatch.setattr(tm.time, "sleep", lambda s: None)
    yield m
    m.srv.shutdown()


GOOD_SKILL = {
    "name": "x", "description": "Post a comment on an issue", "goal": "Leave a review comment", "app": "Browser",
    "inputs": [{"name": "comment", "description": "comment text", "example": "LGTM"}],
    "preconditions": ["Signed in"],
    "steps": [
        {"id": 1, "intent": "Focus the comment box", "action": "click", "target": "comment box", "expect": "cursor"},
        {"id": 2, "intent": "Write the comment", "action": "type", "text": "{{comment}}", "target": "comment box"},
        {"id": 3, "intent": "Submit", "action": "hotkey", "keys": "ctrl+enter", "expect": "comment shown"},
    ],
    "success": "The comment appears", "notes": [],
}


# ----------------------------------------------------------------- keys

def test_normalize_combo():
    assert tm.normalize_combo("Shift + Control + T") == "ctrl+shift+t"
    assert tm.normalize_combo("cmd+option+esc") == "alt+cmd+esc"
    assert tm.normalize_combo("Return") == "enter"
    assert tm.normalize_combo("win+l") == "cmd+l"


def test_risky():
    assert tm.is_risky("Alt+F4") and tm.is_risky("ctrl+W") and tm.is_risky("win+l") and tm.is_risky("cmd+q")
    assert not tm.is_risky("ctrl+s") and not tm.is_risky("enter")


def test_key_name():
    assert tm.key_name(FakeKey(char="A")) == "a"
    assert tm.key_name(FakeKey(char="\x13")) == "s"  # ctrl+s as control char
    assert tm.key_name(FakeKey(name="ctrl_l")) == "ctrl"
    assert tm.key_name(FakeKey(name="shift_r")) == "shift"
    assert tm.key_name(FakeKey(name="alt_gr")) == "altgr"
    assert tm.key_name(FakeKey(name="page_down")) == "page_down"
    assert tm.key_name(FakeKey(vk=65)) == "a"


# ----------------------------------------------------------------- json + skills

def test_extract_json():
    assert tm.extract_json('{"a": 1}') == {"a": 1}
    assert tm.extract_json('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert tm.extract_json('here: {"a": "}"} trailing') == {"a": "}"}
    with pytest.raises(ValueError):
        tm.extract_json("no json")
    with pytest.raises(ValueError):
        tm.extract_json("[1, 2]")


def test_validate_skill():
    assert tm.validate_skill(json.loads(json.dumps(GOOD_SKILL))) == []
    bad = json.loads(json.dumps(GOOD_SKILL))
    bad["steps"][0]["action"] = "teleport"
    bad["steps"][2]["keys"] = ""
    bad["steps"][1]["text"] = "{{unknown}}"
    errs = tm.validate_skill(bad)
    assert any("action must be" in e for e in errs)
    assert any("needs 'keys'" in e for e in errs)
    assert any("undeclared input" in e for e in errs)
    assert tm.validate_skill({"steps": "x"})


def test_skill_markdown_has_frontmatter():
    s = tm.normalize_skill(json.loads(json.dumps(GOOD_SKILL)), "post-comment")
    md = tm.skill_markdown(s)
    assert md.startswith("---\nname: post-comment\ndescription: \"Post a comment on an issue\"\n---")
    assert "--input comment=" in md and "1. **Focus the comment box**" in md


def test_substitute():
    assert tm.substitute("Hi {{ who }}, {{missing}}", {"who": "Ann"}) == "Hi Ann, {{missing}}"


def test_skill_name_validation(home):
    with pytest.raises(tm.TaskMimicError):
        tm.skill_dir("../etc")
    with pytest.raises(tm.TaskMimicError):
        tm.skill_dir("")
    assert tm.skill_dir("ok-name_1").name == "ok-name_1"


# ----------------------------------------------------------------- run-time validation

def test_check_action():
    assert tm.check_action({"status": "done"}) == ("done", {})
    st, a = tm.check_action({"status": "act", "action": {"type": "click", "x": "500", "y": 20}})
    assert st == "act" and a["x"] == 500.0
    with pytest.raises(ValueError):
        tm.check_action({"status": "act", "action": {"type": "click"}})
    with pytest.raises(ValueError):
        tm.check_action({"status": "act", "action": {"type": "click", "x": 1200, "y": 1}})
    with pytest.raises(ValueError):
        tm.check_action({"status": "act", "action": {"type": "type", "x": 1, "y": 1, "text": ""}})
    with pytest.raises(ValueError):
        tm.check_action({"status": "act", "action": {"type": "hotkey", "keys": "ctrl+banana"}})
    with pytest.raises(ValueError):
        tm.check_action({"status": "act", "action": {"type": "hotkey", "keys": "ctrl+alt+s"}})  # abort key
    with pytest.raises(ValueError):
        tm.check_action({"status": "maybe"})
    _, a = tm.check_action({"status": "act", "action": {"type": "scroll", "x": 1, "y": 1, "dy": -500}})
    assert a["dy"] == -30
    _, a = tm.check_action({"status": "act", "action": {"type": "wait", "seconds": 99}})
    assert a["seconds"] == 10
    _, a = tm.check_action({"status": "act", "action": {"type": "hotkey", "keys": "Ctrl+Shift+F5"}})
    assert a["keys"] == "Ctrl+Shift+F5"


# ----------------------------------------------------------------- recorder (no screen)

def run_rec(tmp_path, fn, **kw):
    rec = tm.Recorder(tmp_path / "rec", None, interval=0.05, **kw)
    th = threading.Thread(target=rec.capture_loop, daemon=True)
    th.start()
    fn(rec)
    time.sleep(0.2)
    rec.stop_event.set()
    th.join(2)
    rec.close()
    return [e for e in tm.load_events(tmp_path / "rec") if e["type"] != "frame"]


def type_str(rec, s):
    for ch in s:
        rec.on_key_press("space" if ch == " " else ch.lower(), None if ch == " " else ch)


def test_recorder_text_and_shortcuts(tmp_path):
    def act(rec):
        rec.on_click(10, 20, FakeKey(name="left"), True)
        rec.on_click(10, 20, FakeKey(name="left"), False)  # release ignored
        type_str(rec, "Helo")
        rec.on_key_press("backspace", None)
        type_str(rec, "lo World")
        rec.on_key_press("enter", None)
        rec.on_key_press("ctrl", None)
        rec.on_key_press("s", "\x13")
        rec.on_key_release("s")
        rec.on_key_release("ctrl")
        rec.on_key_press("shift", None)
        rec.on_key_press("a", "A")  # shift+letter is typing, not a shortcut
        rec.on_key_release("shift")
        rec.on_key_press("tab", None)
    evs = run_rec(tmp_path, act)
    kinds = [(e["type"], e.get("text") or e.get("keys")) for e in evs]
    assert kinds == [("click", None), ("type", "Hello World"), ("key", "enter"), ("hotkey", "ctrl+s"),
                     ("type", "A"), ("key", "tab")]
    assert evs[0]["x"] == 10 and evs[0]["y"] == 20


def test_recorder_redacts_text(tmp_path):
    evs = run_rec(tmp_path, lambda r: (type_str(r, "secret"), r.flush_all()), record_text=False)
    assert evs == [dict(evs[0], text="<6 chars redacted>", redacted=True)]
    assert "secret" not in (tmp_path / "rec" / "events.jsonl").read_text()


def test_recorder_pause_and_scroll(tmp_path):
    def act(rec):
        rec.on_scroll(5, 5, 0, -1)
        rec.on_scroll(5, 5, 0, -2)
        rec.toggle_pause()
        type_str(rec, "pwd")
        rec.on_click(1, 1, FakeKey(name="left"), True)
        rec.toggle_pause()
        rec.on_click(2, 2, FakeKey(name="right"), True)
    evs = run_rec(tmp_path, act)
    assert [e["type"] for e in evs] == ["scroll", "pause", "resume", "right_click"]
    assert evs[0]["dy"] == -3 and "t_last" not in evs[0]


def test_double_click_dedup(tmp_path):
    def act(rec):
        rec.on_click(50, 50, FakeKey(name="left"), True)
        rec.on_click(51, 50, FakeKey(name="left"), True)
    run_rec(tmp_path, act)
    lines, _ = tm.build_timeline(tmp_path / "rec")
    assert len(lines) == 1 and "double_click" in lines[0]


def test_drop_trailing_ctrl_c(tmp_path):
    p = tmp_path / "events.jsonl"
    evs = [{"type": "click", "x": 1, "y": 1, "t": 1}, {"type": "hotkey", "keys": "ctrl+c", "t": 2},
           {"type": "frame", "frame": "0002.jpg", "t": 3}]
    p.write_text("".join(json.dumps(e) + "\n" for e in evs))
    tm._drop_trailing_stop_keys(p)
    assert [e["type"] for e in map(json.loads, p.read_text().splitlines())] == ["click", "frame"]


def test_timeline_with_frames(tmp_path):
    from PIL import Image
    rec = tmp_path / "rec"
    (rec / "frames").mkdir(parents=True)
    for i in range(1, 31):
        Image.new("RGB", (200, 100), (i * 8, 0, 0)).save(rec / "frames" / f"{i:04d}.jpg")
    evs = [{"type": "frame", "frame": "0001.jpg", "t": 0, "reason": "start"}]
    for i in range(2, 30):
        evs.append({"type": "click", "x": 500, "y": 500, "t": i, "frame": f"{i:04d}.jpg"})
    evs.append({"type": "frame", "frame": "0030.jpg", "t": 99, "reason": "end"})
    (rec / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs) + '{"torn')
    lines, images = tm.build_timeline(rec, max_frames=8)
    assert len(lines) == 28
    assert len(images) == 8 and images[-1][0] == "Final screen after the task"
    # click marker drawn at the centre
    ring = (100 + 9, 50)  # on the ring around the click point (radius 10 px at this size)
    assert images[0][1].getpixel(ring)[2] > 40 and Image.open(rec / "frames" / "0002.jpg").getpixel(ring)[2] < 10


# ----------------------------------------------------------------- providers

def test_provider_resolution(home, monkeypatch):
    with pytest.raises(tm.TaskMimicError, match="no model provider"):
        tm.resolve_provider(None)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    assert tm.resolve_provider(None)[0] == "github"
    assert tm.resolve_provider("copilot")[0] == "github"
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert tm.resolve_provider(None)[0] == "gemini"  # gemini preferred when both exist
    assert tm.resolve_provider("ollama")[3] is None
    with pytest.raises(tm.TaskMimicError, match="needs OPENAI_API_KEY"):
        tm.resolve_provider("openai")
    with pytest.raises(tm.TaskMimicError, match="unknown provider"):
        tm.resolve_provider("nope")


def test_gemini_request_and_parse(home, mock, monkeypatch):
    from PIL import Image
    monkeypatch.setenv("GEMINI_API_KEY", "gkey")
    mock.gemini({"ok": True})
    m = tm.Model("gemini")
    assert m.ask_json("sys", ["hello", Image.new("RGB", (10, 10))]) == {"ok": True}
    req = mock.requests[0]
    assert req["path"] == "/models/gemini-3.6-flash:generateContent"
    assert req["headers"]["x-goog-api-key"] == "gkey"
    parts = req["body"]["contents"][0]["parts"]
    assert parts[0] == {"text": "hello"} and parts[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert req["body"]["system_instruction"]["parts"][0]["text"] == "sys"
    assert "temperature" not in json.dumps(req["body"])  # deprecated on current Gemini models


def test_gemini_blocked(home, mock, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gkey")
    mock.replies.append((200, {"promptFeedback": {"blockReason": "SAFETY"}}, {}))
    with pytest.raises(tm.TaskMimicError, match="SAFETY"):
        tm.Model("gemini").ask_json("s", ["x"])


def test_github_request_retry_and_json_fallback(home, mock, monkeypatch):
    from PIL import Image
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
    mock.error(429, "slow down", {"Retry-After": "1"})
    mock.error(400, "Unrecognized request argument: response_format")
    mock.openai('```json\n{"a": 1}\n```')
    m = tm.Model("copilot")
    assert m.ask_json("sys", ["hi", Image.new("RGB", (8, 8))]) == {"a": 1}
    first, last = mock.requests[0], mock.requests[-1]
    assert first["path"] == "/chat/completions"
    assert first["headers"]["Authorization"] == "Bearer ghp_tok"
    assert first["body"]["model"] == "openai/gpt-4.1"
    assert first["body"]["response_format"] == {"type": "json_object"}
    assert "response_format" not in last["body"]
    content = last["body"]["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_http_errors_are_friendly_and_hide_key(home, mock, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRET")
    mock.error(401, "bad key")
    with pytest.raises(tm.TaskMimicError) as e:
        tm.Model("openai").ask_json("s", ["x"])
    assert "check your API key" in str(e.value) and "sk-SECRET" not in str(e.value)


def test_json_repair_roundtrip(home, mock, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    mock.openai("I think the answer is yes")
    mock.openai({"fixed": 1})
    assert tm.Model("openai").ask_json("s", ["x"]) == {"fixed": 1}
    assert "not valid JSON" in json.dumps(mock.requests[1]["body"])


def test_network_error(home, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(tm.time, "sleep", lambda s: None)
    with pytest.raises(tm.TaskMimicError, match="network error"):
        tm.Model("openai", timeout=2).ask_json("s", ["x"])


# ----------------------------------------------------------------- learn end to end (mock model)

def make_recording(home, name="post-comment"):
    from PIL import Image
    rec = tm.skill_dir(name) / "recordings" / "20260101-000000"
    (rec / "frames").mkdir(parents=True)
    Image.new("RGB", (320, 200), "white").save(rec / "frames" / "0001.jpg")
    Image.new("RGB", (320, 200), "gray").save(rec / "frames" / "0002.jpg")
    evs = [{"type": "frame", "frame": "0001.jpg", "t": 0, "reason": "start"},
           {"type": "click", "x": 400, "y": 600, "t": 1, "frame": "0001.jpg"},
           {"type": "type", "text": "LGTM", "t": 2, "frame": "0001.jpg"},
           {"type": "hotkey", "keys": "ctrl+enter", "t": 3, "frame": "0001.jpg"},
           {"type": "frame", "frame": "0002.jpg", "t": 4, "reason": "end"}]
    (rec / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
    return rec


def test_learn_fixes_invalid_then_saves(home, mock, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    make_recording(home)
    bad = json.loads(json.dumps(GOOD_SKILL))
    bad["steps"][1]["text"] = "{{msg}}"  # undeclared input -> model is asked to fix it
    mock.gemini(bad)
    mock.gemini(GOOD_SKILL)
    s = tm.learn("post-comment", None, None, False, 10, "comment on an issue")
    assert s["name"] == "post-comment" and len(s["steps"]) == 3
    assert "undeclared input" in json.dumps(mock.requests[1]["body"])
    first = json.dumps(mock.requests[0]["body"])
    assert "typed \\\"LGTM\\\"" in first and "comment on an issue" in first
    d = tm.skill_dir("post-comment")
    assert (d / "SKILL.md").read_text().startswith("---\nname: post-comment")
    assert tm.load_skill("post-comment")["steps"][1]["text"] == "{{comment}}"
    out = tm.cmd_export("post-comment", str(home / "export"))
    assert {p.name for p in out.iterdir()} == {"SKILL.md", "skill.json", "taskmimic.py"}


def test_learn_without_recording(home):
    with pytest.raises(tm.TaskMimicError, match="no recordings"):
        tm.learn("nothing", "ollama", None, False, 10, None)


def test_cli_list_show(home, capsys, mock, monkeypatch):
    assert tm.main(["list"]) == 0
    assert "No skills yet" in capsys.readouterr().out
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    make_recording(home)
    mock.gemini(GOOD_SKILL)
    assert tm.main(["learn", "post-comment"]) == 0
    assert tm.main(["list"]) == 0
    assert "3 steps" in capsys.readouterr().out
    assert tm.main(["show", "post-comment"]) == 0
    assert "## Steps" in capsys.readouterr().out
    assert tm.main(["show", "bad/name"]) == 1
    assert tm.main(["run", "post-comment", "--input", "oops"]) == 1
