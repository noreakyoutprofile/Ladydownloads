# TikTok / YouTube / Facebook Downloader Bot — with Premium Tiers + Admin Bot

Two bots sharing one database:
- **Download bot** — what your users talk to (send a link, pick quality, get MP4/MP3)
- **Admin bot** — only you can use it (approve payments, set the QR code, see stats, manually extend/ban users)

## Plans

| Plan | Price | Downloads/day | Max quality |
|---|---|---|---|
| Free | — | 5 | 720p |
| Premium | $2/month | 10 | 1080p |
| Premium+ | $5/month | 30 | 4K |

Edit these anytime in `config.py` (`TIERS` dict).

## Setup

1. **Create two bots** with [@BotFather](https://t.me/BotFather): one for downloads, one for admin (e.g. `MyDownloaderBot` and `MyDownloaderAdminBot`).

2. **Get your Telegram numeric ID** by messaging [@userinfobot](https://t.me/userinfobot). This is what makes the admin bot yours only.

3. **Install FFmpeg** (needed for MP3 + merging video/audio):
   - Ubuntu/Debian: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`

4. **Install Python deps**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set environment variables**
   ```bash
   export DOWNLOAD_BOT_TOKEN="123:abc-your-download-bot-token"
   export ADMIN_BOT_TOKEN="456:def-your-admin-bot-token"
   export ADMIN_IDS="123456789"   # your Telegram numeric ID; comma-separate for multiple admins
   ```

6. **Run both bots together**
   ```bash
   python run_all.py
   ```
   (Or run `python download_bot.py` and `python admin_bot.py` separately in two terminals if you prefer.)

7. **Set your payment QR code**: open a chat with your *admin* bot, send it your QR code image (e.g. your bank/e-wallet's KHQR code — ABA, Wing, Bakong, etc. all work since it's just an image) with the caption `/setqr`. That image is what users see when they tap Upgrade.

## How the upgrade/payment flow works

1. User runs `/upgrade` on the download bot → picks a plan → sees your QR code + amount.
2. User pays manually (scans the QR in their banking app) and sends a screenshot back in the chat.
3. You get that screenshot in your **admin bot** with ✅ Approve / ❌ Reject buttons.
4. Tap Approve → the user is instantly upgraded, with an expiry date set 30 days out, and gets notified automatically. Tap Reject → they're notified it didn't go through.

This "manual QR + admin confirms" model is common for Cambodia-based bots since it works with any bank/e-wallet's QR (ABA, Wing, Bakong, etc.) without needing a merchant payment-gateway integration.

## Admin bot commands

- `/pending` — list payment requests awaiting approval
- `/setqr` — (send with a QR photo) set the payment QR code
- `/stats` — total users, breakdown by plan, pending count
- `/find <id or @username>` — look up a user's plan/expiry/usage
- `/extend <id> <free|premium2|premium5> <days>` — manually set or extend a plan (useful for refunds, gifts, disputes)
- `/ban <id>` / `/unban <id>` — restrict/unrestrict a user
- `/broadcast <message>` — message every user at once

## User bot commands

- Just send a link — quality buttons appear automatically, filtered to what their plan allows
- `/status` — see plan, downloads left today, expiry date
- `/upgrade` — see plans and pay
- `/quality` — set a default quality/format so future links skip the picker and download instantly. Choose "Always ask me" to go back to the menu each time.
- `/language` — switch between English and Khmer (ខ្មែរ) at any time; the choice is saved per user

## Fixing "Sign in to confirm you're not a bot" (YouTube)

YouTube often blocks downloads from server/datacenter IPs unless the request carries cookies from a real, logged-in browser session. Fix it once:

1. In a normal (non-incognito) browser window, log into YouTube with any Google account.
2. Install a cookie-export extension, e.g. **"Get cookies.txt LOCALLY"** (Chrome/Firefox).
3. While on youtube.com, click the extension and export/download `cookies.txt`.
4. Send that file to your **admin bot** as a document (not a photo) with the caption `/setcookies` — or send the file first, then reply to it with `/setcookies`.

The bot saves it to `COOKIES_PATH` and every download will use it automatically. If YouTube later logs that account out or the cookies expire, just repeat the export and resend — no redeploy needed.

On Railway, also set `COOKIES_PATH=/data/cookies.txt` (same volume as your DB/QR code) so it survives redeploys.

A couple of things worth knowing: this ties downloads to that one Google account, so heavy use could get that account rate-limited or flagged by YouTube, and cookies.txt is sensitive (it's basically a login credential) — never commit it to GitHub, which is why it's already in `.gitignore`.



- Telegram bots can only send files up to **50MB**. For bigger 4K files you'd
  need a self-hosted Telegram Bot API server (supports up to 2GB) — say the word if you want that added.
- `yt-dlp` needs occasional updates as platforms change: `pip install -U yt-dlp`.
- The database is a single SQLite file (`bot.db`) — back it up periodically.
- This is a manual-approval payment flow, not an automated payment gateway — there's no real-time verification that the money actually arrived, so it relies on you checking the screenshot before tapping Approve.
- Respect each platform's terms of service and copyright — this is best used for personal downloads rather than redistribution, and running a paid service around it may have its own legal/tax implications worth checking into locally.

## Deploying for 24/7 uptime

Any VPS with Python 3.9+ and FFmpeg works (DigitalOcean, a cheap Cambodian/SEA VPS provider, etc.). Run `run_all.py` under a process manager like `systemd`, `pm2`, or `supervisor` so it restarts automatically if it crashes.

### Deploying on Railway (from GitHub)

1. **Push this folder to a GitHub repo** (the `.gitignore` already excludes `bot.db`, cached QR images, and `__pycache__`).

2. **In Railway**: New Project → Deploy from GitHub repo → pick this repo.
   Railway will detect Python via Nixpacks. The included `nixpacks.toml` tells it to also install **FFmpeg**, and the `Procfile` tells it to run `python run_all.py`.

3. **Set environment variables** in the Railway service's Variables tab:
   - `DOWNLOAD_BOT_TOKEN`
   - `ADMIN_BOT_TOKEN`
   - `ADMIN_IDS`
   - `DB_PATH` → `/data/bot.db`
   - `QR_DIR` → `/data/qr_codes`
   - `COOKIES_PATH` → `/data/cookies.txt`

4. **Add a Volume** (important!): Railway's filesystem is wiped on every redeploy. Without a volume, your database and QR code would reset every time you push a new commit. In the service → Settings → Volumes, add a volume mounted at `/data`. That's why the variables above point `DB_PATH`/`QR_DIR` there.

5. **Deploy.** Check the Railway logs — you should see `Both bots are running.` Then message your download bot's `/start` to confirm it responds.

6. Re-send your QR to the admin bot with `/setqr` once — it'll now persist across deploys since it's saved to the volume.

One thing to know: Railway bills for uptime, and this app runs 24/7 via polling (not on-demand), so it'll consume hours continuously — check Railway's current pricing/usage plan to make sure that fits your budget.
