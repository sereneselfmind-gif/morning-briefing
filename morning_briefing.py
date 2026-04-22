#!/usr/bin/env python3
"""
Morning Briefing Bot — Beautiful Newsletter Edition
- NewsData.io free tier    → real current news with article images
- Groq Llama 3.3 70B free  → high quality curation and summaries
- Telegraph                → beautiful newsletter landing page + per-article Instant View pages
- Telegram                 → clean HTML summary, all links open as Instant View
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
GROQ_MODEL    = "llama-3.3-70b-versatile"   # better quality, 1000 req/day free

# ── Category default images (Wikimedia Commons direct URLs) ───────────────────
# These are stable, freely licensed images used when no article image is found
DEFAULT_IMAGES = {
    "security":      "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Lock-icon-hi.png/240px-Lock-icon-hi.png",
    "tech":          "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/240px-Python-logo-notext.svg.png",
    "world":         "https://upload.wikimedia.org/wikipedia/commons/thumb/8/80/UN_emblem_blue.svg/240px-UN_emblem_blue.svg.png",
    "grc":           "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Balance_of_justice.png/240px-Balance_of_justice.png",
    "entertainment": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Clapperboard.svg/240px-Clapperboard.svg.png",
    "india":         "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Flag_of_India.svg/320px-Flag_of_India.svg.png",
}

SECTION_META = {
    "security":      ("🔐", "Security & Vulnerabilities",  "Threats, CVEs and patches for your devices."),
    "tech":          ("💻", "Global Tech News",             "Under-reported developments in AI, hardware and open source."),
    "world":         ("🌍", "World Politics",               "Geopolitical shifts beyond the mainstream headlines."),
    "grc":           ("📋", "GRC & Compliance",             "Regulatory updates, enforcement actions and compliance deadlines."),
    "entertainment": ("🎬", "Entertainment",                "OTT, Malayalam & Indian cinema, global film and music."),
    "india":         ("🇮🇳", "India & Kerala",              "Top stories from India and Kerala."),
}

SEVERITY_LABELS = {
    "Critical": "🔴 CRITICAL — Patch immediately",
    "High":     "🟠 HIGH — Action recommended",
    "Medium":   "🟡 MEDIUM — Monitor closely",
    "Low":      "🟢 LOW — Informational",
}


# ── Groq API ──────────────────────────────────────────────────────────────────

def call_groq(prompt: str, retries: int = 3) -> str:
    """Call Groq Llama 3.3 70B with auto-retry on 429."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": "You are a precise intelligence briefing assistant. Always return valid JSON exactly as instructed. No markdown fences, no explanation, no preamble — pure JSON only."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
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
        try:
            return resp.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Groq response: {e}")
    raise RuntimeError(f"Groq still rate-limited after {retries} retries")


def parse_json_response(raw: str) -> list:
    """Safely extract a JSON array from Groq response."""
    text = raw.strip()
    if "```" in text:
        text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```"))
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


# ── NewsData.io ───────────────────────────────────────────────────────────────

SECTION_QUERIES = {
    "security":      {"q": "vulnerability security CVE patch exploit malware",                        "language": "en"},
    "tech":          {"q": "artificial intelligence open source cybersecurity hardware technology",    "language": "en"},
    "world":         {"q": "war conflict election diplomacy geopolitical sanctions",                   "language": "en"},
    "grc":           {"q": "GDPR compliance regulation privacy enforcement data protection DPDP",      "language": "en"},
    "entertainment": {"q": "film cinema OTT streaming music release festival Malayalam Bollywood",     "language": "en"},
    "india":         {"q": "India Kerala", "country": "in",                                           "language": "en"},
}

SECTION_INSTRUCTIONS = {
    "security":      "Focus on CVEs and security threats for macOS Tahoe (Apple M2) and Android 16 (Vivo X300 Pro). Include severity and patch status in detail.",
    "tech":          "Under-reported global tech only. AI policy, open source, hardware, cybersecurity incidents. No PR fluff.",
    "world":         "Geopolitical stories not on mainstream front pages. Conflicts, diplomacy, elections, sanctions.",
    "grc":           "Regulatory updates: ISO, NIST, CERT-In, India DPDP Act, GDPR enforcement, fines.",
    "entertainment": "OTT releases, Malayalam and Indian cinema, global film festivals, music. No celebrity gossip.",
    "india":         "Top Kerala and India general news not covered in the other sections.",
}


def fetch_news(section: str) -> list:
    """Fetch articles from NewsData.io including image URLs."""
    params = {"apikey": NEWSDATA_API_KEY, "size": 10, **SECTION_QUERIES[section]}
    resp   = requests.get("https://newsdata.io/api/1/latest", params=params, timeout=15)
    if not resp.ok:
        print(f"   ⚠️  NewsData [{resp.status_code}]: {resp.text[:200]}")
        return []
    body = resp.json()
    if body.get("status") != "success":
        print(f"   ⚠️  NewsData non-success: {str(body)[:200]}")
        return []
    articles = body.get("results", [])
    print(f"   → {len(articles)} raw articles from API")
    return [
        {
            "title": (a.get("title") or "").strip()[:150],
            "url":   a.get("link", ""),
            "image": a.get("image_url") or "",     # may be empty — handled with defaults
        }
        for a in articles
        if a.get("title") and a.get("link")
    ]


def curate_with_groq(section: str, articles: list, date_str: str) -> list:
    """Ask Groq Llama 3.3 70B to pick best 5 and write rich summaries."""
    needs_severity = (section == "security")
    sev_field      = ', "severity": "High"' if needs_severity else ""
    sev_note       = 'Add "severity": Critical/High/Medium/Low per item.' if needs_severity else ""

    articles_text = "\n".join(f"{i+1}. {a['title']} | {a['url']}" for i, a in enumerate(articles))

    prompt = f"""Date: {date_str}. Briefing section: {section.upper()}.
Instruction: {SECTION_INSTRUCTIONS[section]}
{sev_note}

Articles to choose from:
{articles_text}

Select exactly 5. For each write:
- headline: punchy, under 12 words
- summary: 2 rich sentences of context and significance (NOT just the headline repeated)
- url: copy exactly from above
{f'- severity: one of Critical/High/Medium/Low' if needs_severity else ''}

Return ONLY a JSON array:
[{{"headline":"...","url":"https://...","summary":"..."{sev_field}}},...]"""

    raw = call_groq(prompt)
    try:
        items = parse_json_response(raw)
        # normalise: map summary → detail for compatibility
        for item in items:
            if "summary" in item and "detail" not in item:
                item["detail"] = item.pop("summary")
        return items[:5]
    except Exception as e:
        print(f"   ⚠️  Parse error for '{section}': {e}")
        return [{"headline": a["title"][:80], "url": a["url"], "detail": "", "image": a.get("image","")} for a in articles[:5]]


# ── Telegraph helpers ─────────────────────────────────────────────────────────

def get_telegraph_token() -> str:
    if TOKEN_CACHE_FILE.exists():
        data = json.loads(TOKEN_CACHE_FILE.read_text())
        print("✅ Using cached Telegraph token")
        return data["access_token"]
    print("🔧 Creating Telegraph account...")
    resp = requests.post("https://api.telegra.ph/createAccount", json={
        "short_name": "MorningBrief", "author_name": "Morning Briefing Bot"
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
        "access_token": token, "title": title,
        "author_name": "Morning Briefing", "content": nodes, "return_content": False,
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result}")
    return result["result"]["url"]


def img_node(url: str) -> dict:
    """Return a Telegraph image node."""
    return {"tag": "img", "attrs": {"src": url}}


def publish_article_page(token: str, item: dict, section: str, main_url: str) -> str:
    """
    Beautiful individual article Instant View page.
    Layout: image → section tag → severity → rich summary → source link → back link
    """
    emoji, label, _ = SECTION_META.get(section, ("📌", section, ""))
    headline = item.get("headline", "Untitled")
    detail   = item.get("detail", "")
    src_url  = item.get("url", "")
    severity = item.get("severity", "")
    image    = item.get("image", "") or DEFAULT_IMAGES.get(section, "")

    nodes = []

    # Hero image
    if image:
        nodes.append(img_node(image))

    # Section tag
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [f"{emoji}  Morning Briefing  ·  {label}"]}
    ]})

    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})

    # Severity badge
    if severity:
        nodes.append({"tag": "p", "children": [
            {"tag": "b", "children": [SEVERITY_LABELS.get(severity, severity)]}
        ]})
        nodes.append({"tag": "p", "children": [" "]})

    # Rich summary as blockquote
    if detail:
        nodes.append({"tag": "blockquote", "children": [detail]})
        nodes.append({"tag": "p", "children": [" "]})

    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})

    # Source link
    if src_url:
        nodes.append({"tag": "p", "children": [
            "📰  ",
            {"tag": "a", "attrs": {"href": src_url}, "children": ["Read full original article →"]}
        ]})

    nodes.append({"tag": "p", "children": [" "]})

    # Back to main briefing link
    if main_url:
        nodes.append({"tag": "p", "children": [
            "← ",
            {"tag": "a", "attrs": {"href": main_url}, "children": ["Back to Morning Briefing"]}
        ]})

    nodes.append({"tag": "p", "children": [" "]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": ["Morning Briefing · Powered by Groq Llama 3.3 70B + NewsData.io"]}
    ]})

    return publish_to_telegraph(token, headline, nodes)


def publish_main_newsletter(token: str, sections: dict, date_str: str) -> str:
    """
    Beautiful newsletter-style landing page.
    Layout: masthead → table of contents → section cards with images → footer
    All article links go to individual Telegraph Instant View pages.
    """
    nodes = []

    # ── Masthead ──────────────────────────────────────────────────────────────
    nodes.append({"tag": "p", "children": [
        {"tag": "b", "children": ["📰  MORNING BRIEFING"]}
    ]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [f"📅  {date_str}"]}
    ]})
    nodes.append({"tag": "p", "children": [
        "Your daily intelligence digest — curated and summarised."
    ]})
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})
    nodes.append({"tag": "p", "children": [" "]})

    # ── Table of Contents ─────────────────────────────────────────────────────
    nodes.append({"tag": "p", "children": [{"tag": "b", "children": ["In today's briefing:"]}]})
    for key, items in sections.items():
        if not items:
            continue
        emoji, label, _ = SECTION_META.get(key, ("📌", key, ""))
        count = len(items)
        nodes.append({"tag": "p", "children": [f"  {emoji}  {label}  ·  {count} stories"]})
    nodes.append({"tag": "p", "children": [" "]})
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})
    nodes.append({"tag": "p", "children": [" "]})

    # ── Sections ──────────────────────────────────────────────────────────────
    for key, items in sections.items():
        if not items:
            continue

        emoji, label, intro = SECTION_META.get(key, ("📌", key, ""))

        # Section header
        nodes.append({"tag": "h3", "children": [f"{emoji}  {label}"]})

        # Section intro
        nodes.append({"tag": "p", "children": [{"tag": "em", "children": [intro]}]})
        nodes.append({"tag": "p", "children": [" "]})

        # Article cards
        for item in items:
            headline  = item.get("headline", "Untitled")
            detail    = item.get("detail", "")
            severity  = item.get("severity", "")
            tele_url  = item.get("telegraph_url", item.get("url", ""))
            image     = item.get("image", "") or DEFAULT_IMAGES.get(key, "")

            # Article image
            if image:
                nodes.append(img_node(image))

            # Severity badge
            if severity:
                nodes.append({"tag": "p", "children": [
                    {"tag": "b", "children": [SEVERITY_LABELS.get(severity, severity)]}
                ]})

            # Headline as bold link → individual Telegraph page
            if tele_url:
                nodes.append({"tag": "p", "children": [
                    {"tag": "b", "children": [
                        {"tag": "a", "attrs": {"href": tele_url}, "children": [headline]}
                    ]}
                ]})
            else:
                nodes.append({"tag": "p", "children": [{"tag": "b", "children": [headline]}]})

            # Summary as blockquote
            if detail:
                nodes.append({"tag": "blockquote", "children": [detail]})

            nodes.append({"tag": "p", "children": [" "]})

        # Section divider
        nodes.append({"tag": "p", "children": ["· · · · · · · · · · · · · · · · · · · · · · · ·"]})
        nodes.append({"tag": "p", "children": [" "]})

    # ── Footer ────────────────────────────────────────────────────────────────
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": ["Tap any headline to read the full story in Instant View."]}
    ]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [f"Generated automatically · Groq Llama 3.3 70B + NewsData.io · {date_str}"]}
    ]})

    return publish_to_telegraph(token, f"📰 Morning Briefing — {date_str}", nodes)


# ── Telegram ──────────────────────────────────────────────────────────────────

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
            "chat_id": TELEGRAM_CHAT_ID, "text": chunk,
            "parse_mode": "HTML", "disable_web_page_preview": False,
        }, timeout=10)
        print(f"✅ Telegram chunk {i+1}/{len(chunks)} sent" if resp.ok else f"⚠️  Telegram error: {resp.text}")
        if len(chunks) > 1:
            time.sleep(0.5)


def build_telegram_summary(sections: dict, main_url: str, date_str: str) -> str:
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
            tele_url = item.get("telegraph_url", item.get("url", ""))
            severity = item.get("severity", "")
            sev_tag  = f" <code>{escape_html(severity)}</code>" if severity else ""
            lines.append(f"  • <a href='{tele_url}'>{headline}</a>{sev_tag}" if tele_url else f"  • {headline}{sev_tag}")
        lines.append("")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{main_url}'><b>Open full newsletter →</b></a>",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY", "NEWSDATA_API_KEY"] if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

    date_str = datetime.now().strftime("%A, %d %B %Y")
    print(f"\n{'='*54}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*54}\n")

    token = get_telegraph_token()

    # Step 1 — Fetch and curate all sections
    sections      = {}
    section_order = ["security", "tech", "world", "grc", "entertainment", "india"]

    for section in section_order:
        print(f"🔍 [{section.upper()}] Fetching news...")
        articles = fetch_news(section)
        if not articles:
            print(f"   ⚠️  No articles, skipping\n")
            sections[section] = []
            continue
        print(f"   🤖 Curating with Groq Llama 3.3 70B...")
        items = curate_with_groq(section, articles, date_str)
        # Carry over image URLs from raw articles where available
        for item in items:
            for art in articles:
                if art["url"] == item.get("url") and art.get("image"):
                    item["image"] = art["image"]
                    break
        sections[section] = items
        print(f"   ✅ {len(items)} items selected\n")
        time.sleep(12)   # respect Groq TPM limit

    total = sum(len(v) for v in sections.values())
    print(f"✅ Curation complete — {total} items\n")

    # Step 2 — Publish a placeholder main page first (to get the URL for back links)
    print("📡 Creating main briefing page placeholder...")
    placeholder_nodes = [{"tag": "p", "children": ["Loading..."]}]
    main_url = publish_to_telegraph(token, f"📰 Morning Briefing — {date_str}", placeholder_nodes)
    print(f"   Main URL: {main_url}\n")

    # Step 3 — Publish individual article pages (with back link to main)
    print("📄 Publishing individual article pages...")
    for section, items in sections.items():
        for item in items:
            try:
                tele_url = publish_article_page(token, item, section, main_url)
                item["telegraph_url"] = tele_url
                print(f"   ✅ {item['headline'][:55]}...")
                time.sleep(0.6)
            except Exception as e:
                print(f"   ⚠️  Article page failed: {e}")
                item["telegraph_url"] = item.get("url", "")

    # Step 4 — Publish the real beautiful main newsletter page
    print("\n📰 Publishing main newsletter page...")
    main_url = publish_main_newsletter(token, sections, date_str)
    print(f"✅ Newsletter: {main_url}\n")

    # Step 5 — Send Telegram summary
    summary = build_telegram_summary(sections, main_url, date_str)
    print("📨 Sending to Telegram...")
    send_telegram(summary)

    print(f"\n{'='*54}")
    print("  🎉 Briefing complete!")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
