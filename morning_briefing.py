#!/usr/bin/env python3
"""
Morning Briefing Bot — 4-Section Clean Edition
Sections: Global Politics | India News | Tech News | Malayalam News
Every link is a telegra.ph page = guaranteed Telegram Instant View
Runs on GitHub Actions (US servers, telegra.ph accessible)
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
                  "Chrome/122.0 Safari/537.36"
}

# ── Section definitions ───────────────────────────────────────────────────────
SECTIONS = {
    "politics": {
        "emoji":  "🌍",
        "label":  "Global Politics",
        "intro":  "Geopolitical shifts, diplomacy, conflicts and elections worldwide.",
        "instruction": (
            "Pick the 5 most significant geopolitical stories. Focus on "
            "diplomacy, conflicts, elections, sanctions and international "
            "relations. Avoid mainstream fluff — pick stories with real impact."
        ),
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.dw.com/rss/en-world",
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://feeds.skynews.com/feeds/rss/world.xml",
            "https://news.google.com/rss/search?q=geopolitical+diplomacy+conflict+election&hl=en&gl=US&ceid=US:en",
        ],
        "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/80/UN_emblem_blue.svg/240px-UN_emblem_blue.svg.png",
    },
    "india": {
        "emoji":  "🇮🇳",
        "label":  "India News",
        "intro":  "Top stories from India — politics, economy, society and Kerala.",
        "instruction": (
            "Pick the 5 most important India and Kerala stories of the day. "
            "Cover politics, economy, social issues and major events. "
            "Include at least one Kerala-specific story if available."
        ),
        "feeds": [
            "https://www.thehindu.com/feeder/default.rss",
            "https://indianexpress.com/section/india/feed/",
            "https://feeds.feedburner.com/ndtvnews-top-stories",
            "https://www.thehindu.com/news/national/kerala/feeder/default.rss",
            "https://news.google.com/rss/search?q=India+Kerala+news&hl=en-IN&gl=IN&ceid=IN:en",
        ],
        "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Flag_of_India.svg/320px-Flag_of_India.svg.png",
    },
    "tech": {
        "emoji":  "💻",
        "label":  "Tech News",
        "intro":  "Under-reported developments in AI, open source, hardware and cybersecurity.",
        "instruction": (
            "Pick 5 under-reported or significant tech stories. Focus on "
            "AI policy and research, open source, hardware, cybersecurity "
            "and developer tools. Skip obvious product launches and PR fluff."
        ),
        "feeds": [
            "https://hnrss.org/frontpage",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.theregister.com/headlines.atom",
            "https://www.bleepingcomputer.com/feed/",
            "https://news.google.com/rss/search?q=AI+open+source+cybersecurity+tech+policy&hl=en&gl=US&ceid=US:en",
        ],
        "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/Computer_screen_with_a_terminal_emulator_-_Noun_Project.svg/240px-Computer_screen_with_a_terminal_emulator_-_Noun_Project.svg.png",
    },
    "malayalam": {
        "emoji":  "🌴",
        "label":  "Malayalam News",
        "intro":  "Today's top stories from Kerala in Malayalam sources.",
        "instruction": (
            "Pick the 5 most important Kerala and Malayalam news stories. "
            "Cover local politics, social issues, culture, and major events "
            "from Kerala. Include diverse topics — not all politics."
        ),
        "feeds": [
            "https://www.mathrubhumi.com/rss",
            "https://www.manoramaonline.com/rss/news.xml",
            "https://www.madhyamam.com/rss/news",
            "https://www.deepika.com/rss/deepikaonline.xml",
            "https://news.google.com/rss/search?q=Kerala+Malayalam&hl=ml&gl=IN&ceid=IN:ml",
        ],
        "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f5/Flag_of_Kerala.svg/320px-Flag_of_Kerala.svg.png",
    },
}

# ── RSS Fetching ──────────────────────────────────────────────────────────────

def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return unescape(text).strip()


def parse_feed(url: str) -> list:
    """Parse RSS/Atom feed. Returns list of {title, url} dicts."""
    try:
        for hdrs in [RSS_HEADERS, {"User-Agent": "python-requests/2.31.0"}]:
            try:
                resp = requests.get(url, headers=hdrs, timeout=12,
                                    allow_redirects=True)
                if resp.ok:
                    break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                continue
        else:
            return []

        if not resp.ok:
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return []

        ns       = {"atom": "http://www.w3.org/2005/Atom"}
        articles = []

        # RSS format
        for item in root.findall(".//item"):
            title = clean_html(item.findtext("title", ""))
            link  = (item.findtext("link") or "").strip()
            if title and link and len(title) > 5:
                articles.append({"title": title[:160], "url": link})

        # Atom format
        if not articles:
            for entry in root.findall("atom:entry", ns):
                title   = clean_html(entry.findtext("atom:title", "", ns))
                link_el = entry.find("atom:link", ns)
                link    = link_el.get("href", "") if link_el is not None else ""
                if title and link and len(title) > 5:
                    articles.append({"title": title[:160], "url": link})

        return articles

    except Exception:
        return []


def fetch_section_articles(section_key: str) -> list:
    """Fetch and deduplicate articles from all feeds for a section."""
    feeds        = SECTIONS[section_key]["feeds"]
    all_articles = []
    seen_urls    = set()

    for feed_url in feeds:
        articles = parse_feed(feed_url)
        added = 0
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                all_articles.append(a)
                added += 1
        if added:
            domain = feed_url.split("/")[2][:35]
            print(f"      ✅ {added:2d} articles — {domain}")

    print(f"      → {len(all_articles)} total unique articles")
    return all_articles[:30]


# ── Groq curation ─────────────────────────────────────────────────────────────

def call_groq(prompt: str, retries: int = 3) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    GROQ_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": (
                    "You are a precise news curation assistant. "
                    "Return valid JSON only. No markdown, no explanation, no preamble."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens":  1200,
    }
    for attempt in range(retries):
        resp = requests.post(GROQ_ENDPOINT, headers=headers,
                             json=payload, timeout=60)
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"   ⏳ Rate limited — waiting {wait}s...")
            time.sleep(wait)
            continue
        if not resp.ok:
            raise RuntimeError(
                f"Groq API error {resp.status_code}: {resp.text[:400]}")
        try:
            return resp.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Groq response: {e}")
    raise RuntimeError(f"Groq rate-limited after {retries} retries")


def extract_json_array(raw: str) -> list:
    text = raw.strip()
    if "```" in text:
        text = "\n".join(
            l for l in text.split("\n") if not l.strip().startswith("```"))
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def curate_top5(section_key: str, articles: list, date_str: str) -> list:
    """Ask Groq to select 5 best articles with rich summaries."""
    instruction = SECTIONS[section_key]["instruction"]
    articles_text = "\n".join(
        f"{i+1}. {a['title']} | {a['url']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Date: {date_str}
Section: {SECTIONS[section_key]['label'].upper()}
Task: {instruction}

Articles to choose from:
{articles_text}

Select exactly 5. For each provide:
- headline: clear and punchy, under 12 words
- summary: 2 sentences — what happened and why it matters
- url: copy exactly from the list above

Return ONLY a JSON array:
[{{"headline":"...","url":"https://...","summary":"..."}},...]"""

    raw = call_groq(prompt)
    try:
        items = extract_json_array(raw)
        return items[:5]
    except Exception as e:
        print(f"   ⚠️  Parse error: {e} — using raw titles as fallback")
        return [{"headline": a["title"][:80], "url": a["url"], "summary": ""}
                for a in articles[:5]]


# ── Telegraph ─────────────────────────────────────────────────────────────────

def get_telegraph_token() -> str:
    if TOKEN_CACHE_FILE.exists():
        try:
            data = json.loads(TOKEN_CACHE_FILE.read_text())
            if data.get("access_token"):
                print("✅ Using cached Telegraph token")
                return data["access_token"]
        except Exception:
            pass

    print("🔧 Creating Telegraph account...")
    resp = requests.post(
        "https://api.telegra.ph/createAccount",
        json={"short_name": "MorningBrief", "author_name": "Morning Briefing"},
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createAccount failed: {result}")
    token = result["result"]["access_token"]
    TOKEN_CACHE_FILE.write_text(json.dumps({"access_token": token}))
    print("✅ Telegraph account created and cached")
    return token


def telegraph_post(token: str, title: str, nodes: list) -> str:
    """Publish a Telegraph page and return its URL."""
    resp = requests.post(
        "https://api.telegra.ph/createPage",
        json={
            "access_token":   token,
            "title":          title,
            "author_name":    "Morning Briefing",
            "content":        nodes,
            "return_content": False,
        },
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result}")
    return result["result"]["url"]


def make_article_page(token: str, item: dict,
                      section_key: str, main_url: str) -> str:
    """
    Publish a single article as a clean Telegraph Instant View page.
    Layout: section tag → divider → summary → divider → source link → back link
    """
    sec      = SECTIONS[section_key]
    emoji    = sec["emoji"]
    label    = sec["label"]
    headline = item.get("headline", "Untitled")
    summary  = item.get("summary", "")
    src_url  = item.get("url", "")

    nodes = [
        # Section tag
        {"tag": "p", "children": [
            {"tag": "em", "children": [f"{emoji}  Morning Briefing  ·  {label}"]}
        ]},
        {"tag": "p", "children": ["▬" * 25]},
        {"tag": "p", "children": [" "]},
    ]

    # Summary in a blockquote
    if summary:
        nodes.append({"tag": "blockquote", "children": [summary]})
        nodes.append({"tag": "p", "children": [" "]})

    nodes += [
        {"tag": "p", "children": ["▬" * 25]},
        # Source link
        {"tag": "p", "children": [
            "📰  ",
            {"tag": "a", "attrs": {"href": src_url},
             "children": ["Read original article →"]}
        ]},
        {"tag": "p", "children": [" "]},
        # Back to newsletter
        {"tag": "p", "children": [
            "← ",
            {"tag": "a", "attrs": {"href": main_url},
             "children": ["Back to Morning Briefing"]}
        ]},
        {"tag": "p", "children": [" "]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [
                f"Morning Briefing · {label} · {datetime.now().strftime('%d %b %Y')}"
            ]}
        ]},
    ]

    return telegraph_post(token, headline, nodes)


def make_main_newsletter(token: str, sections_data: dict,
                          date_str: str) -> str:
    """
    Publish the main newsletter landing page on Telegraph.
    Clean layout: masthead → table of contents → section cards → footer.
    All headlines link to individual article Telegraph pages (Instant View).
    """
    nodes = []

    # ── Masthead ──────────────────────────────────────────────────────────────
    nodes += [
        {"tag": "p", "children": [
            {"tag": "b", "children": ["📰  MORNING BRIEFING"]}
        ]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [f"📅  {date_str}"]}
        ]},
        {"tag": "p", "children": [
            "A curated daily digest from top sources — "
            "tap any headline to read in Instant View."
        ]},
        {"tag": "p", "children": ["▬" * 25]},
        {"tag": "p", "children": [" "]},
    ]

    # ── Table of Contents ─────────────────────────────────────────────────────
    nodes.append({"tag": "p", "children": [
        {"tag": "b", "children": ["In today's briefing:"]}
    ]})
    for key, items in sections_data.items():
        if not items:
            continue
        sec = SECTIONS[key]
        nodes.append({"tag": "p", "children": [
            f"  {sec['emoji']}  {sec['label']}  ·  {len(items)} stories"
        ]})
    nodes += [
        {"tag": "p", "children": [" "]},
        {"tag": "p", "children": ["▬" * 25]},
        {"tag": "p", "children": [" "]},
    ]

    # ── Section Cards ─────────────────────────────────────────────────────────
    for key, items in sections_data.items():
        if not items:
            continue
        sec = SECTIONS[key]

        # Section header
        nodes.append({"tag": "h3", "children": [
            f"{sec['emoji']}  {sec['label']}"
        ]})
        nodes.append({"tag": "p", "children": [
            {"tag": "em", "children": [sec["intro"]]}
        ]})
        nodes.append({"tag": "p", "children": [" "]})

        # Article cards
        for item in items:
            headline  = item.get("headline", "Untitled")
            summary   = item.get("summary", "")
            tele_url  = item.get("telegraph_url", item.get("url", ""))

            # Bold headline → individual Telegraph Instant View page
            nodes.append({"tag": "p", "children": [
                {"tag": "b", "children": [
                    {"tag": "a", "attrs": {"href": tele_url},
                     "children": [headline]}
                ]}
            ]})

            # 2-sentence summary
            if summary:
                nodes.append({"tag": "blockquote", "children": [summary]})

            nodes.append({"tag": "p", "children": [" "]})

        # Section divider
        nodes += [
            {"tag": "p", "children": ["·  " * 12]},
            {"tag": "p", "children": [" "]},
        ]

    # ── Footer ────────────────────────────────────────────────────────────────
    nodes += [
        {"tag": "p", "children": ["▬" * 25]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [
                "Sources: BBC · Al Jazeera · DW · The Hindu · Indian Express · "
                "NDTV · Hacker News · Ars Technica · Mathrubhumi · Manorama"
            ]}
        ]},
        {"tag": "p", "children": [
            {"tag": "em", "children": [
                f"Curated by Groq Llama 3.3 70B · {date_str}"
            ]}
        ]},
    ]

    return telegraph_post(
        token, f"📰 Morning Briefing — {date_str}", nodes)


# ── Telegram ──────────────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram_message(text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": False,
    }, timeout=10)
    if not resp.ok:
        print(f"   ⚠️  Telegram error: {resp.text[:200]}")
    return resp.ok


def build_telegram_message(sections_data: dict,
                            main_url: str, date_str: str) -> str:
    """
    Clean Telegram summary message.
    Each bullet → its own Telegraph page = guaranteed Instant View.
    """
    SECTION_HEADERS = {
        "politics":  "🌍 <b>Global Politics</b>",
        "india":     "🇮🇳 <b>India News</b>",
        "tech":      "💻 <b>Tech News</b>",
        "malayalam": "🌴 <b>Malayalam News</b>",
    }

    lines = [
        "📰 <b>Morning Briefing</b>",
        f"<i>{date_str}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for key, items in sections_data.items():
        if not items:
            continue
        lines.append(SECTION_HEADERS.get(key, f"<b>{key}</b>"))
        for item in items:
            headline  = escape_html(item.get("headline", "Untitled"))
            tele_url  = item.get("telegraph_url", item.get("url", ""))
            lines.append(
                f"  • <a href='{tele_url}'>{headline}</a>"
                if tele_url else f"  • {headline}"
            )
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📖 <a href='{main_url}'><b>Open full newsletter →</b></a>",
        "<i>All links open as Instant View</i>",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY"]
               if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

    date_str = datetime.now().strftime("%A, %d %B %Y")
    section_order = ["politics", "india", "tech", "malayalam"]

    print(f"\n{'='*54}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*54}\n")

    token = get_telegraph_token()

    # ── Step 1: Fetch and curate ───────────────────────────────────────────────
    sections_data = {}
    for key in section_order:
        sec = SECTIONS[key]
        print(f"\n{sec['emoji']} [{sec['label'].upper()}]")
        print(f"   Fetching from {len(sec['feeds'])} sources...")

        articles = fetch_section_articles(key)
        if not articles:
            print("   ⚠️  No articles found — skipping")
            sections_data[key] = []
            continue

        print(f"   🤖 Curating top 5 with Groq Llama 3.3 70B...")
        items = curate_top5(key, articles, date_str)
        sections_data[key] = items
        print(f"   ✅ {len(items)} items curated")
        time.sleep(15)   # Groq TPM limit

    total = sum(len(v) for v in sections_data.values())
    print(f"\n✅ Curation complete — {total} items total\n")

    # ── Step 2: Create placeholder main page (for back links) ─────────────────
    print("📡 Creating main page placeholder...")
    main_url = telegraph_post(
        token,
        f"📰 Morning Briefing — {date_str}",
        [{"tag": "p", "children": ["Loading..."]}]
    )
    print(f"   → {main_url}\n")

    # ── Step 3: Publish individual article Instant View pages ─────────────────
    print("📄 Publishing article pages to Telegraph...")
    for key in section_order:
        items = sections_data.get(key, [])
        sec   = SECTIONS[key]
        for item in items:
            try:
                tele_url = make_article_page(token, item, key, main_url)
                item["telegraph_url"] = tele_url
                print(f"   ✅ {sec['emoji']} {item['headline'][:50]}...")
                time.sleep(0.6)
            except Exception as e:
                print(f"   ⚠️  Failed: {e}")
                item["telegraph_url"] = item.get("url", "")

    # ── Step 4: Publish beautiful main newsletter page ─────────────────────────
    print("\n📰 Publishing main newsletter page...")
    main_url = make_main_newsletter(token, sections_data, date_str)
    print(f"✅ Newsletter: {main_url}\n")

    # ── Step 5: Send Telegram summary ─────────────────────────────────────────
    message = build_telegram_message(sections_data, main_url, date_str)
    print("📨 Sending to Telegram...")
    if send_telegram_message(message):
        print("✅ Telegram message sent")

    print(f"\n{'='*54}")
    print("  🎉 Done!")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
