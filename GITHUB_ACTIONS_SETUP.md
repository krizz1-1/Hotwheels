# Free GitHub Actions setup

This uses GitHub-hosted Ubuntu runners. It runs for about 5 hours 30 minutes, then starts its next session using GitHub's `workflow_dispatch` event. GitHub can delay, cancel, or queue sessions, so this is not guaranteed 24/7 hosting.

## Before you begin

To remain free, create a **public** GitHub repository. Standard GitHub-hosted Actions runners are free for public repositories. Do not put secrets in files, commits, issue comments, or workflow logs.

## 1. Upload the project

Create a new public repository named `blinkit-hotwheels-bot`, then run these commands inside this folder:

```powershell
git add .
git commit -m "Add Telegram stock-alert bot"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/blinkit-hotwheels-bot.git
git push -u origin main
```

## 2. Add repository secrets

On GitHub, open the repository, then choose:

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Create these secrets (the names must match exactly):

| Name | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram chat ID |
| `TARGET_PINCODE` | Your delivery pincode |
| `TARGET_LAT` | Your delivery latitude |
| `TARGET_LON` | Your delivery longitude |
| `TARGET_LOCALITY` | Your locality name |
| `TARGET_PRODUCT_URLS` | Optional comma-separated Blinkit product URLs |
| `CHECK_INTERVAL_SECONDS` | Start with `20` |
| `SEARCH_QUERY` | `hot wheels` |

Never use your bot token in the public `.env.example` file.

## 3. Start it

Go to `Actions` → `Blinkit Hot Wheels alert bot` → `Run workflow` → `Run workflow`.

The first run installs Chromium and begins monitoring. Check its logs for `24/7 Cloud Sniper is Active`.

## What to expect

- A GitHub-hosted job has a six-hour maximum. This project intentionally hands off at roughly 5 hours 30 minutes.
- The runner is fresh for each session, so browser cookies and stock-history database are not preserved between sessions.
- The backup schedule starts a new session every six hours if a handoff fails, but can be delayed by GitHub.
- Keep the scan interval at 20 seconds initially. Faster scans risk Blinkit throttling or blocking the runner's shared IP address.

For the best alert speed and genuine persistent storage, move to a VPS if you later get a verified payment method.
