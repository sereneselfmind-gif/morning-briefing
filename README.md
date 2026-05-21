# 📰 Morning Briefing Bot

Automated daily intelligence briefing delivered to Telegram at 4:00 AM IST.
Powered by Claude AI + web search. Full briefing published to Telegraph (telegra.ph).

---

## What It Does

Every morning at 4:00 AM IST, GitHub runs this automatically:

1. Claude searches the web across 6 categories
2. Full detailed briefing is published to a Telegraph page
3. Clean HTML summary is sent to your Telegram
4. The Telegram message links to the full Telegraph page

### Categories Covered
- 🔐 Security & Vulnerabilities (macOS Tahoe / Android 16)
- 💻 Global Tech News
- 🌍 World Politics
- 📋 GRC & Compliance
- 🎬 Entertainment
- 🇮🇳 India & Kerala

---

## Repository Structure

```
morning-briefing/
├── morning_briefing.py          # Main script
├── .github/
│   └── workflows/
│       └── briefing.yml         # GitHub Actions schedule
└── README.md                    # This file
```

---

## Setup Guide

### Step 1 — Prerequisites

You need accounts at:
- [GitHub](https://github.com) — to host and run the code (free)
- [Telegram](https://telegram.org) — to receive the briefing
- [Anthropic](https://console.anthropic.com) — for Claude AI API key

---

### Step 2 — Create Your Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Choose a name: e.g. `My Morning Briefing`
4. Choose a username: e.g. `mymorningbrief_bot`
5. Copy the token — looks like: `7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxx`
6. Search for your new bot in Telegram → click **Start**

---

### Step 3 — Get Your Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign in → left sidebar → **API Keys**
3. Click **Create Key** → name it `morning-briefing`
4. Copy the key (starts with `sk-ant-...`)
5. **Recommended:** Set a monthly spend limit under Billing → e.g. $10

---

### Step 4 — Create the GitHub Repository

1. Go to [github.com](https://github.com) → click **+** → **New repository**
2. Name: `morning-briefing`
3. Visibility: **Private** ← important for security
4. Check **Add a README file**
5. Click **Create repository**

---

### Step 5 — Add Secret Keys to GitHub

Never put API keys directly in code. GitHub encrypts and stores them safely.

1. In your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each of these:

| Secret Name          | Value                          |
|----------------------|--------------------------------|
| `TELEGRAM_BOT_TOKEN` | Your BotFather token           |
| `ANTHROPIC_API_KEY`  | Your Anthropic key (sk-ant...) |
| `TELEGRAM_CHAT_ID`   | `326734657`                    |

---

### Step 6 — Upload the Script

1. In your repo → **Add file** → **Create new file**
2. Filename: `morning_briefing.py`
3. Paste the full contents of `morning_briefing.py`
4. Click **Commit changes** → **Commit directly to main**

---

### Step 7 — Create the Workflow File

1. In your repo → **Add file** → **Create new file**
2. In the filename box, type exactly (including the slashes):
   ```
   .github/workflows/briefing.yml
   ```
3. Paste the full contents of `briefing.yml`
4. Click **Commit changes** → **Commit directly to main**

---

### Step 8 — Test It Manually

Don't wait until 4 AM — trigger it now:

1. In your repo → click **Actions** tab
2. Left sidebar → click **Morning Briefing**
3. Click **Run workflow** → **Run workflow** (green button)
4. Click on the running job to see live logs
5. Wait ~60–90 seconds → check your Telegram

---

### Step 9 — Enable 2FA on GitHub (Security)

1. GitHub → top-right avatar → **Settings**
2. Left sidebar → **Password and authentication**
3. Under Two-factor authentication → click **Enable**
4. Follow the prompts (use an authenticator app)

This is the single most important security step.

---

## Schedule

The bot runs at **4:00 AM IST** daily.

| IST Time | UTC Cron         |
|----------|------------------|
| 4:00 AM  | `30 22 * * *`    |
| 5:00 AM  | `30 23 * * *`    |
| 6:00 AM  | `30 0 * * *`     |
| 7:00 AM  | `30 1 * * *`     |

To change the time, edit line 6 of `.github/workflows/briefing.yml`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No Telegram message | Check bot token secret is correct. Make sure you pressed Start on the bot. |
| Actions tab shows failure | Click the failed job → read the error log |
| `ModuleNotFoundError` | The workflow installs dependencies automatically — re-run the job |
| JSON parse error | Rare Claude API issue — re-run manually via workflow_dispatch |
| Telegraph not loading | telegra.ph can be slow — wait a few minutes and retry |
| Billing concerns | Set a spend limit at console.anthropic.com → Billing |

---

## Security Notes

- All API keys are stored as GitHub Encrypted Secrets — never in code
- Repository is private — no public access
- Only official GitHub Actions are used (`actions/checkout`, `actions/setup-python`)
- If a key is ever compromised: revoke it immediately at the source (BotFather or Anthropic console)
- Enable 2FA on GitHub to prevent account takeover

---

## Cost Estimate

Each daily run costs approximately **$0.05–$0.15** in Anthropic API credits,
depending on how much web searching Claude does. Monthly cost: **~$2–$5**.

GitHub Actions is **free** for private repos (up to 2,000 minutes/month).
This job uses ~2 minutes per run = ~60 minutes/month, well within the free tier.
