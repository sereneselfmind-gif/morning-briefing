#!/usr/bin/env python3
"""
Morning Briefing Bot — GitHub Actions Edition
- RSS feeds + Google News  → quality news from top sources
- Groq Llama 3.3 70B       → intelligent curation and rich summaries
- Telegraph                → beautiful newsletter + per-article Instant View
- Telegram                 → clean summary, all links open as Instant View
"""

import os
import re
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from html import unescape

# ── Configuration ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "326734657")
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
TOKEN_CACHE_FILE   = Path.home() / ".telegraph_token.json"

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = "llama-3.3-70b-versatile"

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "Chrome/122.0 Safari/537.36 MorningBriefBot/2.0"
}

# ── Section metadata ──────────────────────────────────────────────────────────
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

SEVERITY_EMOJI = {
    "Critical": "🔴",
    "High":     "🟠",
    "Medium":   "🟡",
    "Low":      "🟢",
}

DEFAULT_IMAGES = {
    "security":      "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Lock-icon-hi.png/240px-Lock-icon-hi.png",
    "tech":          "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/Computer_screen_with_a_terminal_emulator_-_Noun_Project.svg/240px-Computer_screen_with_a_terminal_emulator_-_Noun_Project.svg.png",
    "world":         "https://upload.wikimedia.org/wikipedia/commons/thumb/8/80/UN_emblem_blue.svg/240px-UN_emblem_blue.svg.png",
    "grc":           "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Balance_of_justice.png/240px-Balance_of_justice.png",
    "entertainment": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Clapperboard.svg/240px-Clapperboard.svg.png",
    "india":         "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Flag_of_India.svg/320px-Flag_of_India.svg.png",
}

SECTION_INSTRUCTIONS = {
    "security":      "Focus on CVEs and active threats for macOS Tahoe (Apple M2) and Android 16 (Vivo X300 Pro). Include severity (Critical/High/Medium/Low) and patch status in detail.",
    "tech":          "Under-reported global tech stories only. AI policy, open source projects, hardware, cybersecurity incidents. No PR fluff or product marketing.",
    "world":         "Geopolitical stories not on mainstream front pages. Conflicts, diplomacy, elections, sanctions, trade disputes.",
    "grc":           "Regulatory updates: ISO, NIST, CERT-In, India DPDP Act, GDPR enforcement actions, compliance fines and deadlines.",
    "entertainment": "OTT releases, Malayalam and Indian cinema news, global film festivals, music releases. No celebrity personal gossip.",
    "india":         "Top Kerala and India general news not already covered in security, tech, world, grc, or entertainment.",
}

# ── RSS Feed Sources ──────────────────────────────────────────────────────────
SECTION_FEEDS = {
    "security": {
        "rss": [
            "https://www.bleepingcomputer.com/feed/",
            "https://feeds.feedburner.com/TheHackersNews",
            "https://www.darkreading.com/rss.xml",
            "https://feeds.feedburner.com/securityweek",
        ],
        "google": "https://news.google.com/rss/search?q=CVE+vulnerability+security+patch&hl=en&gl=US&ceid=US:en",
    },
    "tech": {
        "rss": [
            "https://hnrss.org/frontpage",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.theregister.com/headlines.atom",
            "https://feeds.feedburner.com/TechCrunch",
        ],
        "google": "https://news.google.com/rss/search?q=AI+open+source+tech+policy&hl=en&gl=US&ceid=US:en",
    },
    "world": {
        "rss": [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.dw.com/rss/en-world",
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://feeds.feedburner.com/ndtvnews-world",
        ],
        "google": "https://news.google.com/rss/search?q=geopolitical+conflict+diplomacy+election&hl=en&gl=US&ceid=US:en",
    },
    "grc": {
        "rss": [
            "https://www.iapp.org/feed/",
            "https://feeds.feedburner.com/securityweek",
        ],
        "google": "https://news.google.com/rss/search?q=GDPR+DPDP+NIST+compliance+regulation+enforcement&hl=en&gl=US&ceid=US:en",
    },
    "entertainment": {
        "rss": [
            "https://feeds.feedburner.com/ndtvnews-movies",
            "https://variety.com/feed/",
            "https://deadline.com/feed/",
        ],
        "google": "https://news.google.com/rss/search?q=Malayalam+cinema+OTT+release+Bollywood&hl=en-IN&gl=IN&ceid=IN:en",
    },
    "india": {
        "rss": [
            "https://www.thehindu.com/feeder/default.rss",
            "https://feeds.feedburner.com/ndtvnews-top-stories",
            "https://english.mathrubhumi.com/rss",
        ],
        "google": "https://news.google.com/rss/search?q=Kerala+India+news&hl=en-IN&gl=IN&ceid=IN:en",
    },
}


# ── RSS Fetching ──────────────────────────────────────────────────────────────

def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return unescape(text).strip()


def parse_feed(url: str) -> list:
    """Parse RSS/Atom feed, silently skip on any error."""
    try:
        for hdrs in [RSS_HEADERS, {"User-Agent": "python-requests/2.31.0"}]:
            try:
                resp = requests.get(url, headers=hdrs, timeout=12, allow_redirects=True)
                if resp.ok:
                    break
            except requests.exceptions.ConnectionError:
                continue
        else:
            return []

        if not resp.ok:
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return []

        ns       = {"atom": "http://www.w3.org/2005/Atom",
                    "media": "http://search.yahoo.com/mrss/"}
        articles = []

        # RSS format
        for item in root.findall(".//item"):
            title = clean_html(item.findtext("title", ""))
            link  = (item.findtext("link") or "").strip()
            image = ""
            media = item.find("media:content", ns)
            if media is not None:
                image = media.get("url", "")
            enc = item.find("enclosure")
            if not image and enc is not None and "image" in enc.get("type", ""):
                image = enc.get("url", "")
            if title and link:
                articles.append({"title": title[:150], "url": link, "image": image})

        # Atom format
        if not articles:
            for entry in root.findall("atom:entry", ns):
                title   = clean_html(entry.findtext("atom:title", "", ns))
                link_el = entry.find("atom:link", ns)
                link    = link_el.get("href", "") if link_el is not None else ""
                if title and link:
                    articles.append({"title": title[:150], "url": link, "image": ""})

        return articles

    except Exception:
        return []


def fetch_section_news(section: str) -> list:
    """Fetch and deduplicate articles from all sources for a section."""
    feeds        = SECTION_FEEDS.get(section, {})
    all_articles = []
    seen_urls    = set()

    for feed_url in feeds.get("rss", []):
        articles = parse_feed(feed_url)
        added = 0
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                all_articles.append(a)
                added += 1
        if added:
            print(f"      ✅ {added} articles — {feed_url[:55]}")

    gnews = feeds.get("google", "")
    if gnews:
        articles = parse_feed(gnews)
        added = 0
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                all_articles.append(a)
                added += 1
        if added:
            print(f"      ✅ {added} articles — Google News RSS")

    return all_articles[:25]


# ── Groq curation ─────────────────────────────────────────────────────────────

def call_groq(prompt: str, retries: int = 3) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": "You are a precise intelligence briefing assistant. Always return valid JSON exactly as instructed. No markdown fences, no explanation, no preamble."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens":  1200,
    }
    for attempt in range(retries):
        resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=60)
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"   ⏳ Rate limited — waiting {wait}s...")
            time.sleep(wait)
            continue
        if not resp.ok:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:400]}")
        try:
            return resp.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Groq response: {e}")
    raise RuntimeError(f"Groq rate-limited after {retries} retries")


def parse_json_response(raw: str) -> list:
    text = raw.strip()
    if "```" in text:
        text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```"))
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def curate_with_groq(section: str, articles: list, date_str: str) -> list:
    needs_sev = (section == "security")
    sev_field = ', "severity": "High"' if needs_sev else ""
    sev_note  = "Add severity: Critical/High/Medium/Low per item." if needs_sev else ""

    articles_text = "\n".join(
        f"{i+1}. {a['title']} | {a['url']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Date: {date_str}. Section: {section.upper()}.
Instruction: {SECTION_INSTRUCTIONS[section]}
{sev_note}

Articles:
{articles_text}

Select exactly 5 most relevant. For each:
- headline: punchy and specific, under 12 words
- summary: exactly 2 sentences — what happened and why it matters
- url: copy exactly from above
{f'- severity: Critical/High/Medium/Low' if needs_sev else ''}

Return ONLY a valid JSON array:
[{{"headline":"...","url":"https://...","summary":"..."{sev_field}}},...]"""

    raw = call_groq(prompt)
    try:
        items = parse_json_response(raw)
        for item in items:
            if "summary" in item and "detail" not in item:
                item["detail"] = item.pop("summary")
        return items[:5]
    except Exception as e:
        print(f"   ⚠️  Parse error for '{section}': {e}")
        return [{"headline": a["title"][:80], "url": a["url"], "detail": ""}
                for a in articles[:5]]


# ── Telegraph ─────────────────────────────────────────────────────────────────

def get_telegraph_token() -> str:
    if TOKEN_CACHE_FILE.exists():
        data = json.loads(TOKEN_CACHE_FILE.read_text())
        print("✅ Using cached Telegraph token")
        return data["access_token"]
    print("🔧 Creating Telegraph account...")
    resp = requests.post("https://api.telegra.ph/createAccount", json={
        "short_name": "MorningBrief", "author_name": "Morning Briefing Bot"
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createAccount failed: {result}")
    token = result["result"]["access_token"]
    TOKEN_CACHE_FILE.write_text(json.dumps({"access_token": token}))
    print(f"✅ Telegraph token cached")
    return token


def publish_to_telegraph(token: str, title: str, nodes: list) -> str:
    resp = requests.post("https://api.telegra.ph/createPage", json={
        "access_token": token, "title": title,
        "author_name": "Morning Briefing",
        "content": nodes, "return_content": False,
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result}")
    return result["result"]["url"]


def img_node(url: str) -> dict:
    return {"tag": "img", "attrs": {"src": url}}


def publish_article_page(token: str, item: dict, section: str, main_url: str) -> str:
    """Beautiful individual article Instant View page."""
    emoji, label, _ = SECTION_META.get(section, ("📌", section, ""))
    headline = item.get("headline", "Untitled")
    detail   = item.get("detail", "")
    src_url  = item.get("url", "")
    severity = item.get("severity", "")
    image    = item.get("image", "") or DEFAULT_IMAGES.get(section, "")

    nodes = []

    if image:
        nodes.append(img_node(image))

    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [f"{emoji}  Morning Briefing  ·  {label}"]}
    ]})
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})

    if severity:
        nodes.append({"tag": "p", "children": [
            {"tag": "b", "children": [SEVERITY_LABELS.get(severity, severity)]}
        ]})
        nodes.append({"tag": "p", "children": [" "]})

    if detail:
        nodes.append({"tag": "blockquote", "children": [detail]})
        nodes.append({"tag": "p", "children": [" "]})

    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})

    if src_url:
        nodes.append({"tag": "p", "children": [
            "📰  ",
            {"tag": "a", "attrs": {"href": src_url}, "children": ["Read full original article →"]}
        ]})

    nodes.append({"tag": "p", "children": [" "]})

    if main_url:
        nodes.append({"tag": "p", "children": [
            "← ",
            {"tag": "a", "attrs": {"href": main_url}, "children": ["Back to Morning Briefing"]}
        ]})

    nodes.append({"tag": "p", "children": [" "]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": ["Morning Briefing · Groq Llama 3.3 70B · RSS + Google News"]}
    ]})

    return publish_to_telegraph(token, headline, nodes)


def publish_main_newsletter(token: str, sections: dict, date_str: str) -> str:
    """Beautiful newsletter landing page."""
    nodes = []

    # Masthead
    nodes.append({"tag": "p", "children": [
        {"tag": "b", "children": ["📰  MORNING BRIEFING"]}
    ]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [f"📅  {date_str}"]}
    ]})
    nodes.append({"tag": "p", "children": [
        "Your daily intelligence digest — curated from top sources worldwide."
    ]})
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})
    nodes.append({"tag": "p", "children": [" "]})

    # Table of contents
    nodes.append({"tag": "p", "children": [{"tag": "b", "children": ["In today's briefing:"]}]})
    for key, items in sections.items():
        if not items:
            continue
        emoji, label, _ = SECTION_META[key]
        nodes.append({"tag": "p", "children": [f"  {emoji}  {label}  ·  {len(items)} stories"]})
    nodes.append({"tag": "p", "children": [" "]})
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})
    nodes.append({"tag": "p", "children": [" "]})

    # Section cards
    for key, items in sections.items():
        if not items:
            continue
        emoji, label, intro = SECTION_META[key]

        nodes.append({"tag": "h3", "children": [f"{emoji}  {label}"]})
        nodes.append({"tag": "p", "children": [{"tag": "em", "children": [intro]}]})
        nodes.append({"tag": "p", "children": [" "]})

        for item in items:
            headline = item.get("headline", "Untitled")
            detail   = item.get("detail", "")
            severity = item.get("severity", "")
            tele_url = item.get("telegraph_url", item.get("url", ""))
            image    = item.get("image", "") or DEFAULT_IMAGES.get(key, "")

            if image:
                nodes.append(img_node(image))

            if severity:
                nodes.append({"tag": "p", "children": [
                    {"tag": "b", "children": [SEVERITY_LABELS.get(severity, severity)]}
                ]})

            if tele_url:
                nodes.append({"tag": "p", "children": [
                    {"tag": "b", "children": [
                        {"tag": "a", "attrs": {"href": tele_url}, "children": [headline]}
                    ]}
                ]})
            else:
                nodes.append({"tag": "p", "children": [{"tag": "b", "children": [headline]}]})

            if detail:
                nodes.append({"tag": "blockquote", "children": [detail]})

            nodes.append({"tag": "p", "children": [" "]})

        nodes.append({"tag": "p", "children": ["· · · · · · · · · · · · · · · · · · · · · · · ·"]})
        nodes.append({"tag": "p", "children": [" "]})

    # Footer
    nodes.append({"tag": "p", "children": ["▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": ["Tap any headline to read the full story in Instant View."]}
    ]})
    nodes.append({"tag": "p", "children": [
        {"tag": "em", "children": [
            f"Sources: BleepingComputer · HackerNews · BBC · Al Jazeera · The Hindu · Mathrubhumi · Google News · {date_str}"
        ]}
    ]})

    return publish_to_telegraph(token, f"📰 Morning Briefing — {date_str}", nodes)


# ── Telegram ──────────────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(text: str, disable_preview: bool = False):
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": disable_preview,
    }, timeout=10)
    if not resp.ok:
        print(f"   ⚠️  Telegram error: {resp.text[:200]}")
    return resp.ok


def build_telegram_summary(sections: dict, main_url: str, date_str: str) -> str:
    """Compact Telegram summary — each bullet links to its Telegraph Instant View."""
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
            tele_url = item.get("telegraph_url", item.get("url", ""))
            severity = item.get("severity", "")
            sev_tag  = f" {SEVERITY_EMOJI.get(severity,'')}" if severity else ""
            lines.append(
                f"  • <a href='{tele_url}'>{headline}</a>{sev_tag}" if tele_url
                else f"  • {headline}{sev_tag}"
            )
        lines.append("")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{main_url}'><b>Open full newsletter →</b></a>",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY"] if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

    date_str      = datetime.now().strftime("%A, %d %B %Y")
    section_order = ["tech", "world", "grc", "entertainment", "india", "security"]
    display_order = ["security", "tech", "world", "grc", "entertainment", "india"]

    print(f"\n{'='*54}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*54}\n")

    token = get_telegraph_token()

    # Step 1 — Fetch and curate all sections
    sections = {}
    for section in section_order:
        print(f"🔍 [{section.upper()}] Fetching from RSS + Google News...")
        articles = fetch_section_news(section)
        print(f"   → {len(articles)} unique articles collected")

        if not articles:
            print(f"   ⚠️  No articles found, skipping\n")
            sections[section] = []
            continue

        print(f"   🤖 Curating top 5 with Groq Llama 3.3 70B...")
        items = curate_with_groq(section, articles, date_str)

        # Carry over image from raw articles
        url_to_image = {a["url"]: a.get("image", "") for a in articles}
        for item in items:
            if not item.get("image"):
                item["image"] = url_to_image.get(item.get("url", ""), "")

        sections[section] = items
        print(f"   ✅ {len(items)} items selected\n")
        time.sleep(15)

    total = sum(len(v) for v in sections.values())
    print(f"✅ Curation complete — {total} items\n")

    # Step 2 — Publish placeholder main page (for back links)
    print("📡 Creating main page placeholder...")
    main_url = publish_to_telegraph(
        token, f"📰 Morning Briefing — {date_str}",
        [{"tag": "p", "children": ["Loading..."]}]
    )
    print(f"   → {main_url}\n")

    # Step 3 — Publish individual article Instant View pages
    print("📄 Publishing individual article pages...")
    for section in display_order:
        items = sections.get(section, [])
        for item in items:
            try:
                tele_url = publish_article_page(token, item, section, main_url)
                item["telegraph_url"] = tele_url
                print(f"   ✅ {item['headline'][:55]}...")
                time.sleep(0.5)
            except Exception as e:
                print(f"   ⚠️  Article page failed: {e}")
                item["telegraph_url"] = item.get("url", "")

    # Step 4 — Publish the real beautiful main newsletter
    print("\n📰 Publishing main newsletter page...")
    ordered_sections = {k: sections.get(k, []) for k in display_order}
    main_url = publish_main_newsletter(token, ordered_sections, date_str)
    print(f"✅ Newsletter: {main_url}\n")

    # Step 5 — Send Telegram summary
    summary = build_telegram_summary(ordered_sections, main_url, date_str)
    print("📨 Sending to Telegram...")
    send_telegram(summary)

    print(f"\n{'='*54}")
    print("  🎉 Briefing complete!")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
