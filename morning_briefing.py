#!/usr/bin/env python3
"""
Morning Briefing Bot — 100% Free Edition
- NewsData.io free tier  → fetches real current news (200 req/day free)
- Gemini 2.0 Flash free  → summarises and formats each section
- Telegraph              → publishes full briefing as a beautiful page
- Telegram               → sends clean HTML summary
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
NEWSDATA_API_KEY   = os.environ.get("NEWSDATA_API_KEY", "")
TOKEN_CACHE_FILE   = Path.home() / ".telegraph_token.json"

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

# ── NewsData.io helpers ────────────────────────────────────────────────────────

SECTION_QUERIES = {
    "security": {
        "q":        "CVE vulnerability macOS Android security patch",
        "category": "technology",
        "language": "en",
    },
    "tech": {
        "q":        "AI policy open source hardware cybersecurity",
        "category": "technology",
        "language": "en",
    },
    "world": {
        "q":        "geopolitical conflict diplomacy election sanctions",
        "category": "politics",
        "language": "en",
    },
    "grc": {
        "q":        "GDPR NIST ISO compliance regulation DPDP CERT-In enforcement",
        "category": "technology",
        "language": "en",
    },
    "entertainment": {
        "q":        "OTT Malayalam cinema film festival music release",
        "category": "entertainment",
        "language": "en",
    },
    "india": {
        "q":        "India Kerala news",
        "category": "top",
        "country":  "in",
        "language": "en",
    },
}


def fetch_news(section: str) -> list[dict]:
    """Fetch top articles from NewsData.io for a section."""
    params = {
        "apikey":   NEWSDATA_API_KEY,
        "size":     10,
        **SECTION_QUERIES[section],
    }
    resp = requests.get(
        "https://newsdata.io/api/1/latest",
        params=params,
        timeout=15,
    )
    if not resp.ok:
        print(f"⚠️  NewsData error for '{section}': {resp.status_code} {resp.text[:200]}")
        return []

    data = resp.json()
    articles = data.get("results", [])

    # Return simplified list for Gemini to process
    simplified = []
    for a in articles:
        simplified.append({
            "title":       a.get("title", ""),
            "description": a.get("description", "") or "",
            "url":         a.get("link", ""),
            "source":      a.get("source_name", ""),
            "published":   a.get("pubDate", ""),
        })
    return simplified


# ── Gemini helpers ─────────────────────────────────────────────────────────────

def call_gemini(prompt: str) -> str:
    """Call Gemini 2.0 Flash (free tier, no grounding needed) and return text."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     0.1,
            "maxOutputTokens": 2048,
        },
    }
    resp = requests.post(
        GEMINI_ENDPOINT,
        params={"key": GEMINI_API_KEY},
        json=payload,
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Gemini API error {resp.status_code}: {resp.text[:500]}"
        )
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(
            f"Unexpected Gemini response: {e}\n{json.dumps(data)[:400]}"
        )


def gemini_pick_top5(section: str, articles: list[dict], date_str: str) -> list[dict]:
    """Ask Gemini to pick the best 5 articles and return structured JSON."""

    SECTION_INSTRUCTIONS = {
        "security":      "Focus on CVEs and threats for macOS Tahoe (Apple M2) and Android 16. Include severity (Critical/High/Medium/Low) and patch status in the detail.",
        "tech":          "Pick under-reported tech stories only. AI policy, open source, hardware, cybersecurity incidents. No PR fluff or product launches.",
        "world":         "Pick geopolitical stories NOT on mainstream front pages. Emerging conflicts, diplomacy, elections, sanctions.",
        "grc":           "Pick regulatory updates: ISO, NIST, CERT-In, DPDP Act, GDPR enforcement actions, compliance deadlines.",
        "entertainment": "Pick OTT releases, Malayalam/Indian cinema news, global film festivals, music releases. No celebrity gossip.",
        "india":         "Pick top Kerala and India general news stories not covered in security/tech/world/grc/entertainment.",
    }

    needs_severity = section == "security"
    severity_note  = (
        'Also add a "severity" field: one of Critical/High/Medium/Low.'
        if needs_severity else ""
    )

    articles_text = json.dumps(articles, indent=2)

    prompt = f"""Today is {date_str}.
You are curating a morning intelligence briefing section: {section.upper()}.
Instructions: {SECTION_INSTRUCTIONS[section]}

Here are raw news articles fetched from a news API:
{articles_text}

Your task:
1. Select exactly 5 of the most relevant and interesting articles
2. Write a concise headline (under 12 words) for each
3. Write a one-sentence detail (context, not a repeat of headline)
4. Use the original article URL exactly as provided
{severity_note}

Return ONLY valid JSON, no markdown, no explanation:
[
  {{"headline": "...", "url": "https://...", "detail": "..."{', "severity": "High"' if needs_severity else ''}}},
  ...
]
(exactly 5 items)"""

    raw  = call_gemini(prompt)
    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text  = "\n".join(lines).strip()

    # Extract JSON array
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        items = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"⚠️  Gemini JSON error for section '{section}': {e}")
        print(f"   Raw: {raw[:400]}")
        # Fallback: return first 5 raw articles as-is
        items = [
            {
                "headline": a["title"][:80],
                "url":      a["url"],
                "detail":   a["description"][:120] if a["description"] else "",
            }
            for a in articles[:5]
        ]

    return items[:5]


# ── Telegraph helpers ──────────────────────────────────────────────────────────

def get_telegraph_token() -> str:
    if TOKEN_CACHE_FILE.exists():
        data = json.loads(TOKEN_CACHE_FILE.read_text())
        print("✅ Using cached Telegraph token")
        return data["access_token"]

    print("🔧 Creating new Telegraph account...")
    resp = requests.post("https://api.telegra.ph/createAccount", json={
        "short_name":  "MorningBrief",
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


def publish_to_telegraph(token: str, title: str, nodes: list) -> str:
    resp = requests.post("https://api.telegra.ph/createPage", json={
        "access_token":  token,
        "title":         title,
        "author_name":   "Morning Briefing",
        "content":       nodes,
        "return_content": False,
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result}")
    return result["result"]["url"]


def build_telegraph_nodes(sections: dict, date_str: str) -> list:
    SECTION_META = {
        "security":      "🔐 Security & Vulnerabilities",
        "tech":          "💻 Global Tech News",
        "world":         "🌍 World Politics",
        "grc":           "📋 GRC & Compliance",
        "entertainment": "🎬 Entertainment",
        "india":         "🇮🇳 India & Kerala",
    }
    nodes = [
        {"tag": "p", "children": [
            {"tag": "em", "children": [f"Daily intelligence briefing — {date_str}"]}
        ]},
        {"tag": "p", "children": ["─────────────────────────"]},
    ]
    for key, items in sections.items():
        nodes.append({"tag": "h3", "children": [SECTION_META.get(key, key)]})
        for idx, item in enumerate(items, 1):
            headline = item.get("headline", "Untitled")
            url      = item.get("url", "")
            detail   = item.get("detail", "")
            severity = item.get("severity", "")

            link     = {"tag": "a", "attrs": {"href": url}, "children": [headline]} if url else headline
            children = [f"{idx}. ", link]
            if severity:
                children += [{"tag": "b", "children": [f" [{severity}]"]}]
            if detail:
                children += [f" — {detail}"]
            nodes.append({"tag": "p", "children": children})

        nodes.append({"tag": "p", "children": [" "]})

    nodes += [
        {"tag": "p", "children": ["─────────────────────────"]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [
                f"Generated by Morning Briefing Bot (Gemini 2.0 Flash + NewsData.io) • {date_str}"
            ]}
        ]},
    ]
    return nodes


# ── Telegram helpers ───────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(text: str):
    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = []
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        resp = requests.post(url, json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     chunk,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        print(
            f"✅ Telegram chunk {i+1}/{len(chunks)} sent"
            if resp.ok else
            f"⚠️  Telegram error: {resp.text}"
        )
        if len(chunks) > 1:
            time.sleep(0.5)


def build_telegram_summary(sections: dict, telegraph_url: str, date_str: str) -> str:
    HEADERS = {
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
        lines.append(HEADERS.get(key, f"<b>{escape_html(key)}</b>"))
        for item in items:
            headline = escape_html(item.get("headline", "Untitled"))
            url      = item.get("url", "")
            severity = item.get("severity", "")
            sev_tag  = f" <code>{escape_html(severity)}</code>" if severity else ""
            line     = f"  • <a href='{url}'>{headline}</a>{sev_tag}" if url else f"  • {headline}{sev_tag}"
            lines.append(line)
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{telegraph_url}'><b>Full briefing on Telegraph →</b></a>",
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set")
    if not NEWSDATA_API_KEY:
        raise EnvironmentError("NEWSDATA_API_KEY is not set")

    date_str = datetime.now().strftime("%A, %d %B %Y")
    print(f"\n{'='*52}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*52}\n")

    sections = {}
    for section in ["security", "tech", "world", "grc", "entertainment", "india"]:
        print(f"🔍 Fetching news: {section}...")
        articles = fetch_news(section)
        print(f"   → {len(articles)} articles fetched")

        if not articles:
            print(f"   ⚠️  No articles for '{section}', skipping")
            sections[section] = []
            continue

        print(f"   🤖 Asking Gemini to pick top 5...")
        items = gemini_pick_top5(section, articles, date_str)
        sections[section] = items
        print(f"   ✅ {len(items)} items selected\n")

        # Respect Gemini free tier rate limit (15 req/min)
        time.sleep(4)

    print("📡 Publishing to Telegraph...")
    token         = get_telegraph_token()
    nodes         = build_telegraph_nodes(sections, date_str)
    telegraph_url = publish_to_telegraph(
        token, f"Morning Briefing — {date_str}", nodes
    )
    print(f"✅ Published: {telegraph_url}\n")

    summary = build_telegram_summary(sections, telegraph_url, date_str)
    print(f"📨 Sending to Telegram...")
    send_telegram(summary)

    print(f"\n{'='*52}")
    print("  🎉 Briefing complete!")
    print(f"{'='*52}\n")


if __name__ == "__main__":
    main()
