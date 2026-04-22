#!/usr/bin/env python3
"""
Morning Briefing Bot — Telegram Web App Edition
- RSS + Google News  → curated news per section
- Groq Llama 3.3 70B → intelligent curation with rich summaries
- GitHub Gist        → stores daily JSON (archive for Web App)
- Telegram           → message + "Open Dashboard" Web App button
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
GIST_TOKEN         = os.environ.get("GIST_TOKEN", "")
GIST_ID            = os.environ.get("GIST_ID", "")          # empty on first run
GH_USERNAME    = os.environ.get("GH_USERNAME", "")  # your GitHub username
REPO_NAME          = os.environ.get("REPO_NAME", "morning-briefing")

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = "llama-3.3-70b-versatile"

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "Chrome/122.0 Safari/537.36"
}

# ── Section definitions ────────────────────────────────────────────────────────
SECTIONS = {
    "politics": {
        "emoji": "🌍", "label": "Global Politics",
        "intro": "Geopolitical shifts, diplomacy, conflicts and elections worldwide.",
        "instruction": (
            "Pick the 5 most significant geopolitical stories. Focus on diplomacy, "
            "conflicts, elections, sanctions and international relations. "
            "Avoid mainstream fluff — pick stories with real impact."
        ),
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.dw.com/rss/en-world",
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://feeds.skynews.com/feeds/rss/world.xml",
            "https://news.google.com/rss/search?q=geopolitical+diplomacy+conflict+election&hl=en&gl=US&ceid=US:en",
        ],
    },
    "india": {
        "emoji": "🇮🇳", "label": "India News",
        "intro": "Top stories from India — politics, economy, society and Kerala.",
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
    },
    "tech": {
        "emoji": "💻", "label": "Tech News",
        "intro": "Under-reported developments in AI, open source, hardware and cybersecurity.",
        "instruction": (
            "Pick 5 under-reported or significant tech stories. Focus on AI policy "
            "and research, open source, hardware, cybersecurity and developer tools. "
            "Skip obvious product launches and PR fluff."
        ),
        "feeds": [
            "https://hnrss.org/frontpage",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.theregister.com/headlines.atom",
            "https://www.bleepingcomputer.com/feed/",
            "https://news.google.com/rss/search?q=AI+open+source+cybersecurity+tech+policy&hl=en&gl=US&ceid=US:en",
        ],
    },
    "malayalam": {
        "emoji": "🌴", "label": "Malayalam News",
        "intro": "Today's top stories from Kerala in Malayalam sources.",
        "instruction": (
            "Pick the 5 most important Kerala and Malayalam news stories. "
            "Cover local politics, social issues, culture, and major events from Kerala. "
            "Include diverse topics — not all politics."
        ),
        "feeds": [
            "https://www.mathrubhumi.com/rss",
            "https://www.manoramaonline.com/rss/news.xml",
            "https://www.madhyamam.com/rss/news",
            "https://news.google.com/rss/search?q=Kerala+Malayalam&hl=ml&gl=IN&ceid=IN:ml",
        ],
    },
}

SECTION_ORDER = ["politics", "india", "tech", "malayalam"]


# ── RSS Fetching ──────────────────────────────────────────────────────────────

def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return unescape(text).strip()


def parse_feed(url: str) -> list:
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

        for item in root.findall(".//item"):
            title = clean_html(item.findtext("title", ""))
            link  = (item.findtext("link") or "").strip()
            if title and link and len(title) > 5:
                articles.append({"title": title[:100], "url": link})

        if not articles:
            for entry in root.findall("atom:entry", ns):
                title   = clean_html(entry.findtext("atom:title", "", ns))
                link_el = entry.find("atom:link", ns)
                link    = link_el.get("href", "") if link_el is not None else ""
                if title and link and len(title) > 5:
                    articles.append({"title": title[:100], "url": link})

        return articles
    except Exception:
        return []


def fetch_section_articles(section_key: str) -> list:
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
            domain = feed_url.split("/")[2][:40]
            print(f"      ✅ {added:2d} — {domain}")
    print(f"      → {len(all_articles)} total unique articles")
    return all_articles[:15]


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
                "content": "You are a precise news curation assistant. Return valid JSON only. No markdown, no explanation, no preamble."
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
    instruction   = SECTIONS[section_key]["instruction"]
    articles_text = "\n".join(
        f"{i+1}. {a['title']} | {a['url']}"
        for i, a in enumerate(articles)
    )
    prompt = f"""Date: {date_str}
Section: {SECTIONS[section_key]['label'].upper()}
Task: {instruction}

Articles:
{articles_text}

Select exactly 5. For each:
- headline: clear and punchy, under 12 words
- summary: 2 sentences — what happened and why it matters
- url: copy exactly from above

Return ONLY a JSON array:
[{{"headline":"...","url":"https://...","summary":"..."}},...]"""

    raw = call_groq(prompt)
    try:
        return extract_json_array(raw)[:5]
    except Exception as e:
        print(f"   ⚠️  Parse error: {e}")
        return [{"headline": a["title"][:80], "url": a["url"], "summary": ""}
                for a in articles[:5]]


# ── GitHub Gist storage ───────────────────────────────────────────────────────

GIST_FILENAME = "morning_briefing_archive.json"


def load_archive(gist_id: str) -> dict:
    """Load existing archive from Gist."""
    if not gist_id:
        return {}
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {GIST_TOKEN}",
                     "Accept": "application/vnd.github.v3+json"},
            timeout=15,
        )
        if resp.ok:
            files = resp.json().get("files", {})
            if GIST_FILENAME in files:
                content = files[GIST_FILENAME].get("content", "{}")
                return json.loads(content)
    except Exception as e:
        print(f"   ⚠️  Could not load archive: {e}")
    return {}


def save_archive(archive: dict, gist_id: str) -> str:
    """Save archive to Gist. Creates new Gist if gist_id is empty."""
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
    }
    payload = {
        "description": "Morning Briefing Archive — auto-generated daily",
        "public":      True,
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(archive, ensure_ascii=False, indent=2)
            }
        }
    }

    if gist_id:
        # Update existing Gist
        resp = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers=headers, json=payload, timeout=15,
        )
    else:
        # Create new Gist
        resp = requests.post(
            "https://api.github.com/gists",
            headers=headers, json=payload, timeout=15,
        )

    resp.raise_for_status()
    result  = resp.json()
    new_id  = result["id"]
    raw_url = result["files"][GIST_FILENAME]["raw_url"]
    # Strip the revision hash from raw URL to get stable URL
    stable_url = f"https://gist.githubusercontent.com/{GH_USERNAME}/{new_id}/raw/{GIST_FILENAME}"
    return new_id, stable_url


# ── Telegram ──────────────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram_briefing(sections_data: dict, date_str: str,
                            webapp_url: str):
    """Send Telegram message with summary + Web App button."""
    HEADERS = {
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
    for key in SECTION_ORDER:
        items = sections_data.get(key, [])
        if not items:
            continue
        lines.append(HEADERS.get(key, f"<b>{key}</b>"))
        for item in items:
            headline = escape_html(item.get("headline", "Untitled"))
            url      = item.get("url", "")
            lines.append(
                f"  • <a href='{url}'>{headline}</a>" if url
                else f"  • {headline}"
            )
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "<i>Tap the button below to open the full dashboard</i>",
    ]

    text = "\n".join(lines)

    payload = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text":    "📊  Open Dashboard",
                    "web_app": {"url": webapp_url}
                }
            ]]
        }
    }

    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json=payload, timeout=10)
    if resp.ok:
        print("✅ Telegram message sent with Web App button")
    else:
        print(f"⚠️  Telegram error: {resp.text[:300]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY",
                            "GIST_TOKEN", "GH_USERNAME"]
               if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

    date_str  = datetime.now().strftime("%A, %d %B %Y")
    date_key  = datetime.now().strftime("%Y-%m-%d")
    webapp_url = f"https://{GH_USERNAME}.github.io/{REPO_NAME}/"

    print(f"\n{'='*54}")
    print(f"  📰 Morning Briefing — {date_str}")
    print(f"{'='*54}\n")

    # Step 1 — Fetch and curate
    sections_data = {}
    for key in SECTION_ORDER:
        sec = SECTIONS[key]
        print(f"\n{sec['emoji']} [{sec['label'].upper()}]")
        print(f"   Fetching from {len(sec['feeds'])} sources...")
        articles = fetch_section_articles(key)
        if not articles:
            print("   ⚠️  No articles — skipping")
            sections_data[key] = []
            continue
        print(f"   🤖 Curating with Groq Llama 3.3 70B...")
        items = curate_top5(key, articles, date_str)
        sections_data[key] = items
        print(f"   ✅ {len(items)} items curated")
        time.sleep(15)

    total = sum(len(v) for v in sections_data.values())
    print(f"\n✅ Curation complete — {total} items\n")

    # Step 2 — Load archive and append today
    print("📦 Loading archive from Gist...")
    archive = load_archive(GIST_ID)
    archive[date_key] = {
        "date":     date_str,
        "sections": sections_data,
    }
    # Keep last 30 days only
    if len(archive) > 30:
        sorted_keys = sorted(archive.keys(), reverse=True)
        archive = {k: archive[k] for k in sorted_keys[:30]}

    # Step 3 — Save to Gist
    print("💾 Saving to GitHub Gist...")
    new_gist_id, gist_raw_url = save_archive(archive, GIST_ID)

    if not GIST_ID:
        print(f"\n{'!'*54}")
        print(f"  NEW GIST CREATED — save this as a GitHub secret:")
        print(f"  GIST_ID = {new_gist_id}")
        print(f"{'!'*54}\n")
    else:
        print(f"✅ Gist updated: https://gist.github.com/{new_gist_id}")

    # Step 4 — Send to Telegram with Web App button
    print(f"\n📨 Sending to Telegram...")
    print(f"   Web App URL: {webapp_url}")
    send_telegram_briefing(sections_data, date_str, webapp_url)

    print(f"\n{'='*54}")
    print("  🎉 Done!")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
