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

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = "llama-3.1-8b-instant"   # 14,400 req/day free

# ── Groq API call ──────────────────────────────────────────────────────────────

def call_groq(prompt: str, retries: int = 3) -> str:
    """Call Groq Llama with auto-retry on 429 rate limit errors."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": "You are a precise news curation assistant. Always return valid JSON exactly as instructed. No markdown fences, no explanation, no preamble."
            },
            {
                "role":    "user",
                "content": prompt,
            }
        ],
        "temperature": 0.1,
        "max_tokens":  1024,   # kept low to stay within 6000 TPM free limit
    }
    for attempt in range(retries):
        resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=60)
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)   # 15s, 30s, 45s
            print(f"   ⏳ Rate limited — waiting {wait}s (retry {attempt+1}/{retries})...")
            time.sleep(wait)
            continue
        if not resp.ok:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Groq response: {e}\n{str(data)[:400]}")
    raise RuntimeError(f"Groq still rate-limited after {retries} retries")


# ── NewsData.io helpers ────────────────────────────────────────────────────────

SECTION_QUERIES = {
    # category filter removed — combining q+category causes 0 results on free tier
    "security": {
        "q":        "vulnerability security CVE patch exploit malware",
        "language": "en",
    },
    "tech": {
        "q":        "artificial intelligence open source cybersecurity hardware technology",
        "language": "en",
    },
    "world": {
        "q":        "war conflict election diplomacy geopolitical sanctions",
        "language": "en",
    },
    "grc": {
        "q":        "GDPR compliance regulation privacy enforcement data protection DPDP",
        "language": "en",
    },
    "entertainment": {
        "q":        "film cinema OTT streaming music release festival Malayalam Bollywood",
        "language": "en",
    },
    "india": {
        "q":        "India Kerala",
        "country":  "in",
        "language": "en",
    },
}


def fetch_news(section: str) -> list:
    """Fetch latest articles from NewsData.io. Returns title + url only to save tokens."""
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
        print(f"   ⚠️  NewsData error [{resp.status_code}]: {resp.text[:300]}")
        return []

    body     = resp.json()
    if body.get("status") != "success":
        print(f"   ⚠️  NewsData non-success: {body.get('results', body)}")
        return []
    articles = body.get("results", [])
    print(f"   → API returned {len(articles)} raw results")
    return [
        {
            "title": a.get("title", "").strip()[:120],   # short title only — keeps tokens low
            "url":   a.get("link", ""),
        }
        for a in articles
        if a.get("title") and a.get("link")
    ]


# ── Groq curation ──────────────────────────────────────────────────────────────

SECTION_INSTRUCTIONS = {
    "security":      "Focus on CVEs and security threats for macOS Tahoe (Apple M2) and Android 16. Include severity (Critical/High/Medium/Low) and patch status in the detail.",
    "tech":          "Pick under-reported global tech stories only. AI policy, open source, hardware, cybersecurity incidents. No PR fluff.",
    "world":         "Pick geopolitical stories not on mainstream front pages. Conflicts, diplomacy, elections, sanctions.",
    "grc":           "Regulatory and compliance updates: ISO, NIST, CERT-In, India DPDP Act, GDPR enforcement, fines.",
    "entertainment": "OTT releases, Malayalam and Indian cinema, global film festivals, music releases. No celebrity gossip.",
    "india":         "Top Kerala and India general news not covered in the other sections above.",
}


def curate_with_groq(section: str, articles: list, date_str: str) -> list:
    """Ask Groq to pick the best 5 articles and return structured JSON."""
    needs_severity = (section == "security")
    severity_field = ', "severity": "High"' if needs_severity else ""
    severity_note  = 'Add "severity": Critical/High/Medium/Low for each item.' if needs_severity else ""

    # Build compact article list string (minimise tokens)
    articles_text = "\n".join(
        f"{i+1}. {a['title']} | {a['url']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Date: {date_str}. Section: {section.upper()}.
Rule: {SECTION_INSTRUCTIONS[section]}
{severity_note}

Articles:
{articles_text}

Pick exactly 5. Write a short headline (<12 words), one-sentence detail, copy URL exactly.
Return ONLY a JSON array, no markdown:
[{{"headline":"...","url":"https://...","detail":"..."{severity_field}}},...]"""

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
        # Graceful fallback
        return [
            {"headline": a["title"][:80], "url": a["url"], "detail": ""}
            for a in articles[:5]
        ]


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
    print(f"✅ Telegraph token cached at {TOKEN_CACHE_FILE}")
    return token


def publish_to_telegraph(token: str, title: str, nodes: list) -> str:
    resp = requests.post("https://api.telegra.ph/createPage", json={
        "access_token":   token,
        "title":          title,
        "author_name":    "Morning Briefing",
        "content":        nodes,
        "return_content": False,
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result}")
    return result["result"]["url"]


def build_telegraph_nodes(sections: dict, date_str: str) -> list:
    SECTION_LABELS = {
        "security":      "🔐 Security & Vulnerabilities",
        "tech":          "💻 Global Tech News",
        "world":         "🌍 World Politics",
        "grc":           "📋 GRC & Compliance",
        "entertainment": "🎬 Entertainment",
        "india":         "🇮🇳 India & Kerala",
    }
    nodes = [
        {"tag": "p", "children": [{"tag": "em", "children": [f"Daily intelligence briefing — {date_str}"]}]},
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
        {"tag": "p", "children": [{"tag": "em", "children": [
            f"Generated by Morning Briefing Bot (Groq Llama + NewsData.io) • {date_str}"
        ]}]},
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
        print(f"✅ Telegram chunk {i+1}/{len(chunks)} sent" if resp.ok else f"⚠️  Telegram error: {resp.text}")
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
    lines = ["📰 <b>Morning Briefing</b>", f"<i>{date_str}</i>", "━━━━━━━━━━━━━━━━━━━━━━", ""]
    for key, items in sections.items():
        if not items:
            continue
        lines.append(HEADERS.get(key, f"<b>{escape_html(key)}</b>"))
        for item in items:
            headline = escape_html(item.get("headline", "Untitled"))
            url      = item.get("url", "")
            severity = item.get("severity", "")
            sev_tag  = f" <code>{escape_html(severity)}</code>" if severity else ""
            lines.append(f"  • <a href='{url}'>{headline}</a>{sev_tag}" if url else f"  • {headline}{sev_tag}")
        lines.append("")
    lines += ["━━━━━━━━━━━━━━━━━━━━━━", f"📖 <a href='{telegraph_url}'><b>Full briefing on Telegraph →</b></a>"]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY", "NEWSDATA_API_KEY"] if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

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
            print(f"   ⚠️  No articles found, skipping\n")
            sections[section] = []
            continue

        print(f"   🤖 Curating with Groq Llama...")
        items = curate_with_groq(section, articles, date_str)
        sections[section] = items
        print(f"   ✅ {len(items)} items selected\n")

        # Wait 12s between Groq calls — stays well within 6000 TPM/min free limit
        time.sleep(12)

    total = sum(len(v) for v in sections.values())
    print(f"✅ Research complete — {total} items\n")

    print("📡 Publishing to Telegraph...")
    token         = get_telegraph_token()
    nodes         = build_telegraph_nodes(sections, date_str)
    telegraph_url = publish_to_telegraph(token, f"Morning Briefing — {date_str}", nodes)
    print(f"✅ Published: {telegraph_url}\n")

    summary = build_telegram_summary(sections, telegraph_url, date_str)
    print(f"📨 Sending to Telegram...")
    send_telegram(summary)

    print(f"\n{'='*52}")
    print("  🎉 Briefing complete!")
    print(f"{'='*52}\n")


if __name__ == "__main__":
    main()
