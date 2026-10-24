#!/usr/bin/env bash
# One-time setup of the public demo on a fresh Ubuntu EC2 server (t3.small or larger), served over HTTPS.
#   curl -fsSL https://raw.githubusercontent.com/Sasanksurya/swiggy-ai-assistant/main/deploy/setup-ec2.sh | bash
# Run it again any time to update to the latest code on GitHub.
set -euo pipefail

REPO="https://github.com/Sasanksurya/swiggy-ai-assistant.git"
DIR="$HOME/swiggy-ai-assistant"

echo "== 1/5 Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo "== 2/5 Swap (2 GB of RAM is tight while the website builds)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

echo "== 3/5 Code"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone "$REPO" "$DIR"; fi
cd "$DIR"

echo "== 4/5 Settings (.env stays on this server, never in Git)"
if [ ! -f .env ]; then
  # A random database password; the database is not reachable from the internet anyway.
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" > .env
  chmod 600 .env
fi
# Lets a plain `docker compose ...` use the demo setup (HTTPS website, everything else private)
grep -q '^COMPOSE_FILE=' .env || \
  echo "COMPOSE_FILE=docker-compose.yml:docker-compose.frontend.yml:docker-compose.aws.yml" >> .env
# Free HTTPS name for this server's current public IP (sslip.io maps 1-2-3-4.sslip.io to 1.2.3.4).
# Refreshed on every run because a stopped and started instance gets a new IP.
IP=$(curl -fsS -m 5 https://checkip.amazonaws.com)
SITE="${IP//./-}.sslip.io"
sed -i '/^SITE_ADDRESS=/d' .env && echo "SITE_ADDRESS=$SITE" >> .env

echo "== 5/5 Build and start (the first build takes about 5-10 minutes)"
sudo docker compose up --build -d
sudo docker image prune -f >/dev/null

echo
echo "Done. Open https://$SITE in your browser (demo data only)."
echo "The first visit can take up to a minute while the free certificate is issued."
echo "Needs ports 80 and 443 open to the internet in the instance's security group."
echo "Check:  sudo docker compose ps     Logs:  sudo docker compose logs -f backend"
