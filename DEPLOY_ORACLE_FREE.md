# Free 24/7 deployment on Oracle Cloud (Mumbai)

This setup runs the bot continuously in Docker. Docker restarts it after a crash or a server reboot. The `data/` directory stores the SQLite database and Chromium profile, so those survive upgrades.

## 1. Create an Oracle Always Free server

1. Sign up for Oracle Cloud Free Tier with a card for verification.
2. Select **India West (Mumbai)** as the home region, if offered.
3. Create a Compute instance using Ubuntu 24.04 and an **Always Free** shape:
   - Preferred: `VM.Standard.A1.Flex`, 2 OCPUs and 12 GB RAM.
   - Fallback: `VM.Standard.E2.1.Micro`.
4. Add an inbound rule for **TCP port 22 only**, restricted to your home public IP if possible. Do not open web ports; this bot does not need them.
5. Download the SSH private key and record the instance public IP address.

Oracle may report that an Always Free shape has no capacity. Retry later; do not select a paid shape unless you intend to be charged.

## 2. Push this folder to a private GitHub repository

From your computer, in this folder:

```powershell
git init
git add .
git commit -m "Deploy Blinkit alert bot"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/blinkit-hotwheels-bot.git
git push -u origin main
```

The included `.gitignore` prevents `.env`, browser data, databases, and logs from being committed. Keep this repository private.

## 3. Install Docker and deploy

Connect to the server (replace the placeholders):

```bash
ssh -i /path/to/ssh-key ubuntu@YOUR_SERVER_IP
```

Install Docker:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
```

Connect again, then clone and configure the bot:

```bash
git clone https://github.com/YOUR-USERNAME/blinkit-hotwheels-bot.git
cd blinkit-hotwheels-bot
cp .env.example .env
nano .env
```

Set your real Telegram token, chat ID, and Blinkit location in `.env`. Save with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`.

Start the bot:

```bash
docker compose up -d --build
docker compose logs -f
```

Use `Ctrl+C` to leave the logs; the bot keeps running.

## 4. Verify and update

```bash
docker compose ps
docker compose logs --tail=100
```

For a later update:

```bash
git pull
docker compose up -d --build
```

## Important limits

Use `CHECK_INTERVAL_SECONDS=15` or `20` first. Faster polling can trigger Blinkit protections or cause account/IP blocking. Telegram delivery and Blinkit inventory propagation can also add delay outside the bot's control.
