"""Telegram public-channel roundup. Single file. python tgdisco.py discover|post|all [--dry-run]"""
"""Keyword taxonomy -> (category, hashtag). First-best score wins; ties by order."""
import re

CATEGORIES = {
    "Crypto & Web3": ("#Crypto", "crypto bitcoin btc ethereum eth blockchain web3 defi nft token airdrop trading binance altcoin wallet"),
    "Tech & Programming": ("#Tech", "programming developer coding python javascript linux software github devops opensource cybersecurity hacking gadgets android ios tech"),
    "AI & Data": ("#AI", "ai artificial intelligence chatgpt gpt llm machine learning neural data science midjourney"),
    "Business & Startups": ("#Business", "business startup entrepreneur investing stocks finance money forex marketing sales freelance income"),
    "News & Politics": ("#News", "news breaking politics government world report headlines daily updates election"),
    "Education & Learning": ("#Education", "education learn course study exam university school tutorial lessons scholarship ielts jobs career"),
    "Languages": ("#Languages", "english language spanish german french japanese vocabulary grammar learn language"),
    "Entertainment & Movies": ("#Movies", "movies movie film series tv show cinema netflix anime cartoon memes funny humor"),
    "Music & Audio": ("#Music", "music songs playlist rap hiphop mp3 podcast audio dj"),
    "Gaming": ("#Gaming", "games gaming gamer steam playstation xbox minecraft esports pubg mobile game"),
    "Sports & Fitness": ("#Sports", "sports football soccer cricket nba fitness gym workout running yoga ipl"),
    "Travel": ("#Travel", "travel trip flights tourism hotel visa destination backpacking cheap flights deals"),
    "Food & Cooking": ("#Food", "food recipe cooking kitchen restaurant baking vegan chef"),
    "Health & Wellness": ("#Health", "health medicine medical doctor wellness mental psychology nutrition diet meditation"),
    "Art & Design": ("#Design", "art design photography illustration graphic ui ux creative drawing wallpaper"),
    "Books & Writing": ("#Books", "books book reading novel literature poetry writing quotes ebook library"),
    "Shopping & Deals": ("#Deals", "deals discount coupon offers sale shopping promo cashback amazon loot"),
    "Lifestyle & Fashion": ("#Lifestyle", "fashion style beauty lifestyle home decor motivation self improvement"),
}
DEFAULT = ("Other", "#Other")
_tok = re.compile(r"[a-z0-9]+")

def classify(*texts):
    words = _tok.findall(" ".join(t or "" for t in texts).lower())
    joined = " " + " ".join(words) + " "
    best, best_score = None, 0
    for name, (_tag, kws) in CATEGORIES.items():
        score = 0
        for kw in kws.split():
            score += joined.count(" " + kw + " ")
        # multiword phrases
        for ph in ("machine learning", "artificial intelligence", "cheap flights", "data science", "mental health", "self improvement"):
            if ph in joined and ph in kws:
                score += 2
        if score > best_score:
            best, best_score = name, score
    if not best:
        return DEFAULT
    return best, CATEGORIES[best][0]

"""Discovery of PUBLIC Telegram channels. Private/hidden channels are not discoverable."""
import re, time, html, requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; tg-discovery/1.0)"}
USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
SKIP_SUFFIX = ("bot",)

def _get(url, timeout=15):
    for i in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 403):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5)
    return None

BLOCK = {"vpn","proxy","v2ray","v2rayng","config","configs","porn","xxx","adult","nsfw","casino","betting","18","hack","cracked","leak","leaks","carding","fishing","phishing","filtershekan"}

def english_ok(*texts):
    t = " ".join(x or "" for x in texts)
    letters = [ch for ch in t if ch.isalpha()]
    if not letters:
        return False
    if sum(1 for ch in letters if ch.isascii()) / len(letters) < 0.85:
        return False
    return not (set(re.findall(r"[a-z0-9]+", t.lower())) & BLOCK)

def valid(u):
    return bool(USER_RE.match(u)) and not u.lower().endswith(SKIP_SUFFIX)

def seeds_from_tgstat(categories, delay=1.0):
    out = []
    for c in categories:
        page = _get(f"https://tgstat.com/en/{c}")
        time.sleep(delay)
        if not page:
            continue
        for u in re.findall(r"tgstat\.com/channel/@([A-Za-z0-9_]+)", page):
            if valid(u) and u not in out:
                out.append(u)
    return out

def mentions(page_html):
    """Usernames mentioned via t.me links in a channel preview (snowball discovery)."""
    found = set(re.findall(r"https?://t\.me/([A-Za-z][A-Za-z0-9_]{4,31})(?:[/\"'?<\s]|$)", page_html))
    return {u for u in found if valid(u) and u.lower() not in {"s", "joinchat", "addstickers", "share", "proxy", "socks"}}

def _num(s):
    s = s.strip().replace(" ", "").upper()
    m = re.match(r"([\d.,]+)([KM]?)", s)
    if not m: return 0
    n = float(m.group(1).replace(",", "") if m.group(2) == "" else m.group(1).replace(",", "."))
    return int(n * {"": 1, "K": 1e3, "M": 1e6}[m.group(2)])

def parse_channel(username, page):
    """Return dict for a public *channel* preview page, else None."""
    if "tgme_channel_info" not in page:
        return None  # user/bot/group or non-existent
    def one(pat):
        m = re.search(pat, page, re.S)
        return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
    title = one(r'tgme_channel_info_header_title"><span[^>]*>(.*?)</span>')
    desc = one(r'tgme_channel_info_description">(.*?)</div>')
    subs = 0
    for val, typ in re.findall(r'counter_value">([^<]*)</span> <span class="counter_type">([^<]*)', page):
        if typ.startswith("subscriber"):
            subs = _num(val)
    dates = re.findall(r'<time[^>]*datetime="([^"]+)"', page)
    return {"username": username, "title": title, "description": desc, "subscribers": subs,
            "last_post": dates[-1] if dates else "", "url": f"https://t.me/{username}"}

def fetch_channel(username):
    page = _get(f"https://t.me/s/{username}")
    if not page:
        return None, set()
    return parse_channel(username, page), mentions(page)

import json, os, time
PATH = os.environ.get("TGDISCO_STATE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"))

def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"channels": {}, "frontier": [], "rejected": {}, "posted": {}, "rr": 0}

def save(st, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True, ensure_ascii=False)

import html, os, requests, datetime as dt

def fmt_subs(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else str(n)

def pick(state, cfg, now=None):
    """Choose next category (round-robin over categories that have unposted channels) and channels."""
    now = now or dt.datetime.utcnow()
    cutoff = (now - dt.timedelta(days=cfg["repost_after_days"])).isoformat()
    by_cat = {}
    for u, c in state["channels"].items():
        if state["posted"].get(u, "") > cutoff:
            continue
        by_cat.setdefault(c["category"], []).append(c)
    cats = sorted(k for k, v in by_cat.items() if k != "Other" and len(v) >= 3)
    if not cats:
        return None, []
    cat = cats[state.get("rr", 0) % len(cats)]
    state["rr"] = state.get("rr", 0) + 1
    chans = sorted(by_cat[cat], key=lambda c: -c["subscribers"])[: cfg["channels_per_post"]]
    return cat, chans

def render(cat, tag, chans):
    lines = [f"<b>{html.escape(cat, quote=False)}</b> {tag}", "Public channels worth a look:", ""]
    for c in chans:
        d = re.sub(r"https?://\S+|t\.me/\S+|@\w+", "", c["description"] or "")
        d = re.sub(r"[\s:|]{2,}", " ", d.replace("\n", " ")).strip(" :-|")
        d = (d[:90] + "...") if len(d) > 90 else d
        lines.append(f"• <a href=\"{c['url']}\">{html.escape(c['title'] or c['username'], quote=False)}</a> ({fmt_subs(c['subscribers'])})" + (f" - {html.escape(d, quote=False)}" if d else ""))
    lines += ["", f"Browse everything in this category: {tag}", "#ChannelDiscovery"]
    text = "\n".join(lines)
    return text[:4090]

def send(token, channel_id, text, button_url=None):
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                      json=dict({"chat_id": channel_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                                **({"reply_markup": {"inline_keyboard": [[{"text": "Browse all channels", "url": button_url}]]}} if button_url else {})))
    if not r.ok:
        raise RuntimeError(f"Telegram API error {r.status_code}: {r.text[:300]}")
    return r.json()

"""Entry point.  python run.py discover | post | all  [--dry-run]"""
import argparse, os, sys, yaml, datetime as dt

def export_catalog(st, path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "catalog.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    chans = [{k: c.get(k, "") for k in ("username", "title", "description", "subscribers", "category", "tag", "found")} for c in st["channels"].values()]
    with open(path, "w") as f:
        json.dump({"updated": dt.datetime.utcnow().isoformat(), "channels": chans}, f, ensure_ascii=False, separators=(",", ":"))

def cfg_load():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")) as f:
        return yaml.safe_load(f)

def do_discover(st, cfg):
    now = dt.datetime.utcnow()
    if not st["frontier"]:
        st["frontier"] = seeds_from_tgstat(cfg["tgstat_categories"]) + list(cfg["extra_seeds"])
        print(f"seeded frontier: {len(st['frontier'])}")
    n = 0
    while st["frontier"] and n < cfg["max_enrich_per_run"]:
        u = st["frontier"].pop(0)
        if u in st["channels"] or u in st["rejected"]:
            continue
        n += 1
        if n % 10 == 0: save(st)
        info, ment = fetch_channel(u)
        import time; time.sleep(0.6)
        if not info:
            st["rejected"][u] = "not-public-channel"; continue
        age_ok = True
        if info["last_post"]:
            try:
                last = dt.datetime.fromisoformat(info["last_post"].replace("Z", "+00:00")).replace(tzinfo=None)
                age_ok = (now - last).days <= cfg["max_age_days_last_post"]
            except ValueError:
                pass
        if info["subscribers"] < cfg["min_subscribers"] or not age_ok:
            st["rejected"][u] = "small-or-inactive"; continue
        if not english_ok(info["title"], info["description"]):
            st["rejected"][u] = "non-english-or-blocked"; continue
        cat, tag = classify(info["title"], info["description"])
        info.update(category=cat, tag=tag, found=now.isoformat())
        st["channels"][u] = info
        for m in ment:
            if m not in st["channels"] and m not in st["rejected"] and m not in st["frontier"]:
                st["frontier"].append(m)
    print(f"enriched {n}; catalog={len(st['channels'])} frontier={len(st['frontier'])}")

def do_post(st, cfg, dry):
    for _ in range(cfg["posts_per_run"]):
        cat, chans = pick(st, cfg)
        if not chans:
            print("nothing to post yet"); return
        tag = CATEGORIES[cat][0]
        text = render(cat, tag, chans)
        if dry:
            print("---- DRY RUN (not sent) ----\n" + text); 
            st["rr"] -= 1  # dry run must not consume rotation
            continue
        token = os.environ.get("BOT_TOKEN"); ch = os.environ.get("CHANNEL_ID") or cfg.get("channel_id")
        if not token or not ch:
            sys.exit("BOT_TOKEN and CHANNEL_ID are required to post")
        send(token, ch, text, cfg.get('miniapp_url') or None)
        now = dt.datetime.utcnow().isoformat()
        for c in chans: st["posted"][c["username"]] = now
        print(f"posted {cat}: {len(chans)} channels")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["discover", "post", "all"]); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(); cfg = cfg_load(); st = load()
    if a.cmd in ("discover", "all"): do_discover(st, cfg)
    export_catalog(st)
    if a.cmd in ("post", "all"): do_post(st, cfg, a.dry_run)
    save(st)
