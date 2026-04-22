#!/usr/bin/env python3
"""
Morning Briefing Bot — Groq + NewsData.io Edition (100% Free)
- NewsData.io free tier   → fetches real current news (200 req/day free)
- Groq free tier (Llama)  → picks top 5 and formats each section
- Telegraph               → publishes full beautiful briefing page
- Telegram                → sends clean HTML summary with Telegraph link
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
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
NEWSDATA_API_KEY   = os.environ.get("NEWSDATA_API_KEY", "")
TOKEN_CACHE_FILE   = Path.home() / ".telegraph_token.json"

# Groq uses OpenAI-compatible API format
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = "llama-3.1-8b-instant"   # 14,400 req/day free — most generous

# ── Groq API call ──────────────────────────────────────────────────────────────

def call_groq(prompt: str) -> str:
    """Call Groq Llama and return the response text."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": "You are a precise news curation assistant. You always return valid JSON exactly as instructed. No markdown, no explanation, no preamble."
            },
            {
                "role":    "user",
                "content": prompt,
            }
        ],
        "temperature": 0.1,
        "max_tokens":  2048,
    }
    resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Groq response structure: {e}\n{str(data)[:400]}")


# ── NewsData.io helpers ────────────────────────────────────────────────────────

SECTION_QUERIES = {
    "security": {
        "q":        "CVE vulnerability macOS Android security patch exploit",
        "category": "technology",
        "language": "en",
    },
    "tech": {
        "q":        "AI policy open source hardware cybersecurity breach",
        "category": "technology",
        "language": "en",
    },
    "world": {
        "q":        "geopolitical conflict diplomacy election sanctions trade",
        "category": "politics",
        "language": "en",
    },
    "grc": {
        "q":        "GDPR NIST ISO compliance regulation data protection enforcement fine",
        "category": "technology",
        "language": "en",
    },
    "entertainment": {
        "q":        "OTT Malayalam cinema film festival music streaming release",
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


def fetch_news(section: str) -> list:
    """Fetch latest articles from NewsData.io for a given section."""
    params = {
        "apikey": NEWSDATA_API_KEY,
        "size":   10,
        **SECTION_QUERIES[section],
    }
    resp = requests.get(
        "https://newsdata.io/api/1/latest",
        params=params,
        timeout=15,
    )
    if not resp.ok:
        print(f"   ⚠️  NewsData error [{resp.status_code}]: {resp.text[:200]}")
        return []

    articles = resp.json().get("results", [])
    return [
        {
            "title":       a.get("title", "").strip(),
            "description": (a.get("description") or "").strip()[:300],
            "url":         a.get("link", ""),
            "source":      a.get("source_name", ""),
            "published":   a.get("pubDate", ""),
        }
        for a in articles
        if a.get("title") and a.get("link")
    ]


# ── Groq curation ──────────────────────────────────────────────────────────────

SECTION_INSTRUCTIONS = {
    "security":      "Focus on CVEs and active security threats for macOS Tahoe (Apple M2) and Android 16. Include severity (Critical/High/Medium/Low) and patch status in the detail field.",
    "tech":          "Pick under-reported global tech stories only. AI policy, open source, hardware, cybersecurity incidents. Exclude PR fluff and product marketing.",
    "world":         "Pick geopolitical stories not on mainstream front pages. Emerging conflicts, diplomatic shifts, elections, sanctions, trade disputes.",
    "grc":           "Pick regulatory and compliance updates: ISO, NIST, CERT-In, India DPDP Act, GDPR enforcement actions, compliance deadlines.",
    "entertainment": "Pick OTT releases, Malayalam and Indian cinema news, global film festivals, music releases. Exclude celebrity personal gossip.",
    "india":         "Pick top Kerala and India general news not already covered in security, tech, world, grc, or entertainment sections.",
}


def curate_with_groq(section: str, articles: list, date_str: str) -> list:
    """Ask Groq to pick the best 5 articles and return structured JSON."""
    needs_severity = (section == "security")
    severity_field = ', "severity": "High"' if needs_severity else ""
    severity_note  = 'Add "severity": Critical/High/Medium/Low based on the article.' if needs_severity else ""

    articles_json = json.dumps(articles, indent=2)

    prompt = f"""Today is {date_str}. You are curating the {section.upper()} section of a morning intelligence briefing.

Instructions: {SECTION_INSTRUCTIONS[section]}

Raw articles from news API:
{articles_json}

Task:
- Select exactly 5 of the most relevant articles from the list above
- Write a short headline under 12 words
- Write a one-sentence detail giving context (do NOT repeat the headline)
- Copy the URL exactly from the article
{severity_note}

Return ONLY a JSON array, no markdown fences, no explanation:
[
  {{"headline": "...", "url": "https://...", "detail": "..."{severity_field}}},
  {{"headline": "...", "url": "https://...", "detail": "..."{severity_field}}},
  {{"headline": "...", "url": "https://...", "detail": "..."{severity_field}}},
  {{"headline": "...", "url": "https://...", "detail": "..."{severity_field}}},
  {{"headline": "...", "url": "https://...", "detail": "..."{severity_field}}}
]"""

    raw  = call_groq(prompt)
    text = raw.strip()

    # Strip accidental markdown fences
    if "```" in text:
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text  = "\n".join(lines).strip()

    # Extract JSON array
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        items = json.loads(text)
        return items[:5]
    except json.JSONDecodeError as e:
        print(f"   ⚠️  JSON parse error for '{section}': {e}")
        print(f"   Raw (first 300 chars): {raw[:300]}")
        # Graceful fallback — use raw article titles
        return [
            {
                "headline": a["title"][:80],
                "url":      a["url"],
                "detail":   a["description"][:150] if a["description"] else "",
            }
            for a in articles[:5]
        ]


# ── Telegraph helpers ──────────────────────────────────────────────────────────

def get_telegraph_token() -> str:
    """Return cached Telegraph token or create a new account."""
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
    """Publish a Telegraph page and return its URL."""
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
    """Build Telegraph DOM nodes from section data."""
    SECTION_LABELS = {
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
        if not items:
            continue
        nodes.append({"tag": "h3", "children": [SECTION_LABELS.get(key, key)]})
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
                f"Generated by Morning Briefing Bot (Groq Llama + NewsData.io) • {date_str}"
            ]}
        ]},
    ]
    return nodes


# ── Telegram helpers ───────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(text: str):
    """Send HTML message to Telegram, splitting if over 4000 chars."""
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
        if resp.ok:
            print(f"✅ Telegram chunk {i+1}/{len(chunks)} sent")
        else:
            print(f"⚠️  Telegram error on chunk {i+1}: {resp.text}")
        if len(chunks) > 1:
            time.sleep(0.5)


def build_telegram_summary(sections: dict, telegraph_url: str, date_str: str) -> str:
    """Build clean HTML summary message for Telegram."""
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
        if not items:
            continue
        lines.append(HEADERS.get(key, f"<b>{escape_html(key)}</b>"))
        for item in items:
            headline = escape_html(item.get("headline", "Untitled"))
            url      = item.get("url", "")
            severity = item.get("severity", "")
            sev_tag  = f" <code>{escape_html(severity)}</code>" if severity else ""
            lines.append(
                f"  • <a href='{url}'>{headline}</a>{sev_tag}" if url
                else f"  • {headline}{sev_tag}"
            )
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{telegraph_url}'><b>Full briefing on Telegraph →</b></a>",
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Validate required environment variables
    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY", "NEWSDATA_API_KEY"] if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

    date_str = datetime.now().strftime("%A, %d %B %Y")
    print(f"\n{'='*52}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*52}\n")

    sections      = {}
    section_order = ["security", "tech", "world", "grc", "entertainment", "india"]

    for section in section_order:
        print(f"🔍 [{section.upper()}] Fetching news...")
        articles = fetch_news(section)
        print(f"   → {len(articles)} articles fetched")

        if not articles:
            print(f"   ⚠️  No articles found, skipping section\n")
            sections[section] = []
            continue

        print(f"   🤖 Curating with Groq Llama...")
        items = curate_with_groq(section, articles, date_str)
        sections[section] = items
        print(f"   ✅ {len(items)} items selected\n")

        # Respect Groq free tier: 30 req/min → wait 2s between calls
        time.sleep(2)

    total = sum(len(v) for v in sections.values())
    print(f"✅ Research complete — {total} items across {len([s for s in sections if sections[s]])} sections\n")

    # Publish to Telegraph
    print("📡 Publishing to Telegraph...")
    token         = get_telegraph_token()
    nodes         = build_telegraph_nodes(sections, date_str)
    telegraph_url = publish_to_telegraph(token, f"Morning Briefing — {date_str}", nodes)
    print(f"✅ Published: {telegraph_url}\n")

    # Send to Telegram
    summary = build_telegram_summary(sections, telegraph_url, date_str)
    print(f"📨 Sending to Telegram (chat: {TELEGRAM_CHAT_ID})...")
    send_telegram(summary)

    print(f"\n{'='*52}")
    print("  🎉 Briefing complete!")
    print(f"{'='*52}\n")


if __name__ == "__main__":
    main()
