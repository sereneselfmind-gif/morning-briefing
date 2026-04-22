#!/usr/bin/env python3
"""
Morning Briefing Bot — Gemini Edition
- Uses Gemini 2.0 Flash with Google Search grounding (free tier)
- Publishes full briefing to Telegraph (telegra.ph)
- Sends clean HTML summary to Telegram
- Auto-creates and caches Telegraph token
"""

import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "326734657")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
TOKEN_CACHE_FILE   = Path.home() / ".telegraph_token.json"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
)

# ── Gemini API call ────────────────────────────────────────────────────────────

def call_gemini(prompt: str) -> str:
    """Call Gemini 2.0 Flash with Google Search grounding and return text."""
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "tools": [
            {"google_search": {}}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
        }
    }

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )

    resp = requests.post(url, json=payload, timeout=120)

    if not resp.ok:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()

    # Extract text from response
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"No candidates in Gemini response: {data}")
        parts = candidates[0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        return text.strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response structure: {e}\n{json.dumps(data)[:500]}")


# ── Telegraph helpers ──────────────────────────────────────────────────────────

def get_telegraph_token() -> str:
    """Return cached token or create a new Telegraph account."""
    if TOKEN_CACHE_FILE.exists():
        data = json.loads(TOKEN_CACHE_FILE.read_text())
        print("✅ Using cached Telegraph token")
        return data["access_token"]

    print("🔧 Creating new Telegraph account...")
    resp = requests.post("https://api.telegra.ph/createAccount", json={
        "short_name": "MorningBrief",
        "author_name": "Morning Briefing Bot",
    }, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createAccount failed: {result}")
    token = result["result"]["access_token"]
    TOKEN_CACHE_FILE.write_text(json.dumps({"access_token": token}))
    print(f"✅ Telegraph account created, token cached at {TOKEN_CACHE_FILE}")
    return token


def publish_to_telegraph(token: str, title: str, content_nodes: list) -> str:
    """Publish content to Telegraph and return the public URL."""
    resp = requests.post("https://api.telegra.ph/createPage", json={
        "access_token": token,
        "title": title,
        "author_name": "Morning Briefing",
        "content": content_nodes,
        "return_content": False,
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result}")
    return result["result"]["url"]


def build_telegraph_nodes(sections: dict, date_str: str) -> list:
    """Convert section dict into Telegraph DOM node format."""
    nodes = []

    nodes.append({
        "tag": "p",
        "children": [{"tag": "em", "children": [f"Daily intelligence briefing — {date_str}"]}]
    })
    nodes.append({"tag": "p", "children": ["─────────────────────────"]})

    SECTION_META = {
        "security":      "🔐 Security & Vulnerabilities",
        "tech":          "💻 Global Tech News",
        "world":         "🌍 World Politics",
        "grc":           "📋 GRC & Compliance",
        "entertainment": "🎬 Entertainment",
        "india":         "🇮🇳 India & Kerala",
    }

    for key, items in sections.items():
        label = SECTION_META.get(key, key)
        nodes.append({"tag": "h3", "children": [label]})

        for idx, item in enumerate(items, 1):
            headline = item.get("headline", "Untitled")
            url      = item.get("url", "")
            detail   = item.get("detail", "")
            severity = item.get("severity", "")

            if url:
                link = {"tag": "a", "attrs": {"href": url}, "children": [headline]}
            else:
                link = headline

            children = [f"{idx}. ", link]
            if severity:
                children += [{"tag": "b", "children": [f" [{severity}]"]}]
            if detail:
                children += [f" — {detail}"]

            nodes.append({"tag": "p", "children": children})

        nodes.append({"tag": "p", "children": [" "]})

    nodes.append({"tag": "p", "children": ["─────────────────────────"]})
    nodes.append({
        "tag": "p",
        "children": [{"tag": "em", "children": [
            f"Generated by Morning Briefing Bot (Gemini 2.0 Flash) • {date_str}"
        ]}]
    })
    return nodes


# ── Telegram helpers ───────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(text: str):
    """Send message to Telegram, auto-splitting if over 4000 chars."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    chunks = []
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.ok:
            print(f"✅ Telegram chunk {i+1}/{len(chunks)} sent")
        else:
            print(f"⚠️  Telegram error on chunk {i+1}: {resp.text}")
        if len(chunks) > 1:
            time.sleep(0.5)


def build_telegram_summary(sections: dict, telegraph_url: str, date_str: str) -> str:
    """Build the HTML-formatted Telegram summary message."""
    SECTION_HEADERS = {
        "security":      "🔐 <b>Security &amp; Vulnerabilities</b>",
        "tech":          "💻 <b>Global Tech News</b>",
        "world":         "🌍 <b>World Politics</b>",
        "grc":           "📋 <b>GRC &amp; Compliance</b>",
        "entertainment": "🎬 <b>Entertainment</b>",
        "india":         "🇮🇳 <b>India &amp; Kerala</b>",
    }

    lines = [
        "📰 <b>Morning Briefing</b>",
        f"<i>{date_str}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for key, items in sections.items():
        header = SECTION_HEADERS.get(key, f"<b>{escape_html(key)}</b>")
        lines.append(header)

        for item in items:
            headline = escape_html(item.get("headline", "Untitled"))
            url      = item.get("url", "")
            severity = item.get("severity", "")
            sev_tag  = f" <code>{escape_html(severity)}</code>" if severity else ""

            if url:
                lines.append(f"  • <a href='{url}'>{headline}</a>{sev_tag}")
            else:
                lines.append(f"  • {headline}{sev_tag}")

        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{telegraph_url}'><b>Full briefing on Telegraph →</b></a>",
    ]

    return "\n".join(lines)


# ── Research with Gemini + Google Search ──────────────────────────────────────

RESEARCH_PROMPT = """You are a research assistant compiling a morning intelligence briefing.
Use Google Search to find TODAY's top stories for each section below.
Today's date is {date}.

SECTIONS AND REQUIREMENTS:

1. security — CVEs and active threats for macOS Tahoe (Apple M2) and Android 16 (Vivo X300 Pro)
   published in the last 24 hours. Each item needs severity (Critical/High/Medium/Low) and patch status.

2. tech — Under-reported global tech developments only. AI policy, open source projects,
   hardware announcements, cybersecurity incidents. No press releases or product launches.

3. world — Geopolitical developments NOT on mainstream front pages. Emerging conflicts,
   diplomatic shifts, elections, sanctions, trade disputes.

4. grc — Regulatory updates globally: ISO standards, NIST frameworks, CERT-In advisories,
   India DPDP Act, GDPR enforcement, global compliance deadlines and fines.

5. entertainment — OTT releases, Malayalam and Indian cinema news, global film festivals,
   music releases. No celebrity personal gossip.

6. india — Top Kerala and India general news not already covered in any section above.

RULES:
- Search Google for each section — use only current, real news from today or yesterday
- Every item must have a real, working URL to the original article
- Headlines must be under 12 words
- detail is one sentence of additional context (not a repeat of the headline)
- Exactly 5 items per section — no more, no less
- For security section, include a "severity" field per item

Return ONLY valid JSON with NO markdown fences, NO preamble, NO explanation.
Exact structure required:
{{
  "security": [
    {{"headline": "...", "url": "https://...", "detail": "...", "severity": "High"}},
    {{"headline": "...", "url": "https://...", "detail": "...", "severity": "Critical"}},
    {{"headline": "...", "url": "https://...", "detail": "...", "severity": "Medium"}},
    {{"headline": "...", "url": "https://...", "detail": "...", "severity": "High"}},
    {{"headline": "...", "url": "https://...", "detail": "...", "severity": "Low"}}
  ],
  "tech":          [{{"headline": "...", "url": "https://...", "detail": "..."}}, ...],
  "world":         [{{"headline": "...", "url": "https://...", "detail": "..."}}, ...],
  "grc":           [{{"headline": "...", "url": "https://...", "detail": "..."}}, ...],
  "entertainment": [{{"headline": "...", "url": "https://...", "detail": "..."}}, ...],
  "india":         [{{"headline": "...", "url": "https://...", "detail": "..."}}, ...]
}}"""


def clean_json(text: str) -> str:
    """Strip markdown fences and extract JSON from Gemini response."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # Find first { and last }
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return text.strip()


def research_briefing() -> dict:
    """Use Gemini with Google Search to compile the full briefing."""
    print("🔍 Researching today's briefing with Gemini + Google Search...")
    print("   (this takes ~30-60 seconds)\n")

    date_str = datetime.now().strftime("%A, %d %B %Y")
    prompt   = RESEARCH_PROMPT.format(date=date_str)

    raw  = call_gemini(prompt)
    text = clean_json(raw)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        print(f"Raw response (first 1000 chars):\n{raw[:1000]}")
        raise

    # Validate structure
    expected = ["security", "tech", "world", "grc", "entertainment", "india"]
    for key in expected:
        if key not in data:
            print(f"⚠️  Missing section: {key}")
        elif len(data[key]) != 5:
            print(f"⚠️  Section '{key}' has {len(data[key])} items (expected 5)")

    return data


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Validate env vars
    if not TELEGRAM_BOT_TOKEN:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set")

    date_str = datetime.now().strftime("%A, %d %B %Y")
    print(f"\n{'='*52}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*52}\n")

    # 1. Research all sections
    sections = research_briefing()
    total    = sum(len(v) for v in sections.values())
    print(f"✅ Research complete — {total} items across {len(sections)} sections\n")

    # 2. Publish full briefing to Telegraph
    print("📡 Publishing to Telegraph...")
    token         = get_telegraph_token()
    nodes         = build_telegraph_nodes(sections, date_str)
    telegraph_url = publish_to_telegraph(
        token, f"Morning Briefing — {date_str}", nodes
    )
    print(f"✅ Published: {telegraph_url}\n")

    # 3. Build and send Telegram summary
    summary = build_telegram_summary(sections, telegraph_url, date_str)
    print(f"📨 Sending to Telegram (chat: {TELEGRAM_CHAT_ID})...")
    send_telegram(summary)

    print(f"\n{'='*52}")
    print("  🎉 Briefing complete!")
    print(f"{'='*52}\n")


if __name__ == "__main__":
    main()
