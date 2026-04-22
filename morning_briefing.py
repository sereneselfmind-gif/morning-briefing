#!/usr/bin/env python3
"""
Morning Briefing Bot — Groq + NewsData.io Edition (100% Free)
- NewsData.io free tier   → fetches real current news (200 req/day free)
- Groq free tier (Llama)  → picks top 5 and formats each section
- Telegraph               → each article gets its own Telegraph page (Instant View)
- Telegram                → clean HTML summary; all links open as Instant View
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
        "max_tokens":  1024,
    }
    for attempt in range(retries):
        resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=60)
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
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

    body = resp.json()
    if body.get("status") != "success":
        print(f"   ⚠️  NewsData non-success: {str(body)[:300]}")
        return []
    articles = body.get("results", [])
    print(f"   → API returned {len(articles)} raw results")
    return [
        {
            "title": a.get("title", "").strip()[:120],
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

    if "```" in text:
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text  = "\n".join(lines).strip()

    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        items = json.loads(text)
        return items[:5]
    except json.JSONDecodeError as e:
        print(f"   ⚠️  JSON parse error for '{section}': {e}")
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
    """Publish a Telegraph page and return its URL."""
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


def publish_article_to_telegraph(token: str, item: dict, section_label: str) -> str:
    """
    Publish a single news item as its own Telegraph page.
    Clean article card layout — opens as Instant View in Telegram.
    """
    headline = item.get("headline", "Untitled")
    detail   = item.get("detail", "")
    src_url  = item.get("url", "")
    severity = item.get("severity", "")

    SEVERITY_BARS = {
        "Critical": "🔴 CRITICAL — Patch immediately",
        "High":     "🟠 HIGH — Action recommended",
        "Medium":   "🟡 MEDIUM — Monitor closely",
        "Low":      "🟢 LOW — Informational",
    }

    nodes = []

    # Section tag
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [f"Morning Briefing  ·  {section_label}"]}
    ]})

    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})

    # Severity badge
    if severity:
        sev_text = SEVERITY_BARS.get(severity, f"⚪ {severity.upper()}")
        nodes.append({"tag": "p", "children": [
            {"tag": "b", "children": [sev_text]}
        ]})

    # Summary as blockquote
    if detail:
        nodes.append({"tag": "blockquote", "children": [detail]})

    nodes.append({"tag": "p", "children": [" "]})
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})

    # Source link
    if src_url:
        nodes.append({"tag": "p", "children": [
            "📰  Read the full story:  ",
            {"tag": "a", "attrs": {"href": src_url}, "children": [src_url[:60] + "..." if len(src_url) > 60 else src_url]}
        ]})

    nodes.append({"tag": "p", "children": [" "]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": ["Part of the Morning Briefing newsletter · Powered by Groq + NewsData.io"]}
    ]})

    return publish_to_telegraph(token, headline, nodes)


def build_main_telegraph_page(sections: dict, date_str: str, token: str) -> str:
    """
    Build the main newsletter-style daily briefing Telegraph page.
    Beautiful layout with section headers, blockquotes, severity badges.
    Every article link opens its own Telegraph Instant View page.
    """
    SECTION_META = {
        "security":      ("🔐", "Security & Vulnerabilities",  "Threats, CVEs and patches for your devices."),
        "tech":          ("💻", "Global Tech News",             "Under-reported developments in AI, hardware and open source."),
        "world":         ("🌍", "World Politics",               "Geopolitical shifts beyond the mainstream headlines."),
        "grc":           ("📋", "GRC & Compliance",             "Regulatory updates, enforcement actions and compliance deadlines."),
        "entertainment": ("🎬", "Entertainment",                "OTT, Malayalam & Indian cinema, global film and music."),
        "india":         ("🇮🇳", "India & Kerala",              "Top stories from India and Kerala."),
    }

    SEVERITY_BARS = {
        "Critical": "🔴 CRITICAL",
        "High":     "🟠 HIGH",
        "Medium":   "🟡 MEDIUM",
        "Low":      "🟢 LOW",
    }

    # ── Header ────────────────────────────────────────────────────────────────
    nodes = [
        {"tag": "p", "children": [
            {"tag": "b", "children": ["MORNING BRIEFING"]}
        ]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [f"📅  {date_str}"]}
        ]},
        {"tag": "p", "children": ["Your daily intelligence digest — curated and summarised."]},
        {"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]},
        {"tag": "p", "children": [" "]},
    ]

    # ── Sections ──────────────────────────────────────────────────────────────
    for key, items in sections.items():
        if not items:
            continue

        emoji, label, intro = SECTION_META.get(key, ("📌", key, ""))

        # Section header
        nodes.append({"tag": "h3", "children": [f"{emoji}  {label}"]})

        # Section intro line
        if intro:
            nodes.append({"tag": "p", "children": [
                {"tag": "em", "children": [intro]}
            ]})

        nodes.append({"tag": "p", "children": [" "]})

        # Each article as a blockquote card
        for item in items:
            headline  = item.get("headline", "Untitled")
            detail    = item.get("detail", "")
            severity  = item.get("severity", "")
            tele_url  = item.get("telegraph_url", item.get("url", ""))

            card_children = []

            # Severity badge on its own line for security items
            if severity:
                sev_label = SEVERITY_BARS.get(severity, f"⚪ {severity.upper()}")
                card_children.append({"tag": "b", "children": [sev_label]})
                card_children.append(" | ")

            # Headline as bold link
            if tele_url:
                card_children.append({
                    "tag": "a",
                    "attrs": {"href": tele_url},
                    "children": [{"tag": "b", "children": [headline]}]
                })
            else:
                card_children.append({"tag": "b", "children": [headline]})

            # Detail line
            if detail:
                card_children.append(" | ")
                card_children.append(detail)

            nodes.append({"tag": "blockquote", "children": card_children})
            nodes.append({"tag": "p", "children": [" "]})

        # Section divider
        nodes.append({"tag": "p", "children": ["· · · · · · · · · · · · · · · · · · ·"]})
        nodes.append({"tag": "p", "children": [" "]})

    # ── Footer ────────────────────────────────────────────────────────────────
    nodes += [
        {"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [
                f"Generated automatically • Groq Llama + NewsData.io • {date_str}"
            ]}
        ]},
        {"tag": "p", "children": [
            {"tag": "em", "children": ["Tap any headline above to read the full story in Instant View."]}
        ]},
    ]

    return publish_to_telegraph(token, f"📰 Morning Briefing — {date_str}", nodes)


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
            "disable_web_page_preview": False,   # allow Telegraph previews
        }, timeout=10)
        print(f"✅ Telegram chunk {i+1}/{len(chunks)} sent" if resp.ok else f"⚠️  Telegram error: {resp.text}")
        if len(chunks) > 1:
            time.sleep(0.5)


def build_telegram_summary(sections: dict, main_telegraph_url: str, date_str: str) -> str:
    """
    Build Telegram HTML summary.
    Every bullet links to its own telegra.ph page → opens as Instant View.
    """
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
            headline  = escape_html(item.get("headline", "Untitled"))
            tele_url  = item.get("telegraph_url", item.get("url", ""))
            severity  = item.get("severity", "")
            sev_tag   = f" <code>{escape_html(severity)}</code>" if severity else ""
            # Link goes to telegra.ph page → Instant View in Telegram
            lines.append(
                f"  • <a href='{tele_url}'>{headline}</a>{sev_tag}" if tele_url
                else f"  • {headline}{sev_tag}"
            )
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{main_telegraph_url}'><b>Full briefing on Telegraph →</b></a>",
    ]
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

    SECTION_LABELS = {
        "security":      "🔐 Security & Vulnerabilities",
        "tech":          "💻 Global Tech News",
        "world":         "🌍 World Politics",
        "grc":           "📋 GRC & Compliance",
        "entertainment": "🎬 Entertainment",
        "india":         "🇮🇳 India & Kerala",
    }

    # Step 1 — Fetch and curate all sections
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
        time.sleep(12)   # respect Groq 6000 TPM/min free limit

    total = sum(len(v) for v in sections.values())
    print(f"✅ Research complete — {total} items\n")

    # Step 2 — Publish each article as its own Telegraph page (= Instant View)
    print("📡 Publishing individual article pages to Telegraph...")
    token = get_telegraph_token()

    for section, items in sections.items():
        label = SECTION_LABELS.get(section, section)
        for item in items:
            try:
                tele_url = publish_article_to_telegraph(token, item, label)
                item["telegraph_url"] = tele_url
                print(f"   ✅ {item['headline'][:50]}...")
                time.sleep(0.5)   # be gentle with Telegraph API
            except Exception as e:
                print(f"   ⚠️  Failed to publish article: {e}")
                item["telegraph_url"] = item.get("url", "")   # fallback to original

    # Step 3 — Publish main briefing page (links to individual Telegraph pages)
    print("\n📡 Publishing main briefing page...")
    main_url = build_main_telegraph_page(sections, date_str, token)
    print(f"✅ Main page: {main_url}\n")

    # Step 4 — Send Telegram summary
    summary = build_telegram_summary(sections, main_url, date_str)
    print(f"📨 Sending to Telegram...")
    send_telegram(summary)

    print(f"\n{'='*52}")
    print("  🎉 Briefing complete!")
    print(f"{'='*52}\n")


if __name__ == "__main__":
    main()
