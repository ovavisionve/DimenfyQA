#!/usr/bin/env bash
# setup-ssl.sh — Obtain a Let's Encrypt certificate via DuckDNS (free subdomain).
#
# Prerequisites:
#   1. Create a free account at https://www.duckdns.org (login with Google/GitHub).
#   2. Create a subdomain, e.g. "dimenfy" → set IP to your VPS IP.
#   3. Copy your DuckDNS token from the dashboard.
#   4. Ports 80 and 443 open on the VPS firewall.
#   5. Docker and Docker Compose installed.
#
# Usage:
#   chmod +x scripts/setup-ssl.sh
#   sudo ./scripts/setup-ssl.sh dimenfy YOUR_DUCKDNS_TOKEN
#
#   This will configure HTTPS for: dimenfy.duckdns.org

set -euo pipefail

SUBDOMAIN="${1:-}"
DUCKDNS_TOKEN="${2:-}"

if [ -z "$SUBDOMAIN" ] || [ -z "$DUCKDNS_TOKEN" ]; then
    echo "Usage: $0 <duckdns-subdomain> <duckdns-token>"
    echo "Example: $0 dimenfy abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    echo ""
    echo "Get your subdomain and token at: https://www.duckdns.org"
    exit 1
fi

DOMAIN="${SUBDOMAIN}.duckdns.org"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_CONF="$PROJECT_DIR/nginx/nginx.conf"
NGINX_INIT_CONF="$PROJECT_DIR/nginx/nginx-init.conf"
CERTBOT_WEBROOT="$PROJECT_DIR/nginx/certbot-webroot"

echo "==> Setting up HTTPS for: $DOMAIN"

# 1. Confirm DuckDNS IP is set correctly
echo "==> Verifying DuckDNS points to this server..."
VPS_IP=$(curl -s https://api.ipify.org)
DNS_IP=$(dig +short "$DOMAIN" | tail -1)
echo "    VPS IP:  $VPS_IP"
echo "    DNS IP:  $DNS_IP"
if [ "$VPS_IP" != "$DNS_IP" ]; then
    echo "WARNING: DNS does not point to this server yet."
    echo "         Go to https://www.duckdns.org and set the IP to: $VPS_IP"
    echo "         Then wait ~1 minute and re-run this script."
    echo ""
    read -r -p "Continue anyway? (y/N) " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

# 2. Install certbot and the DuckDNS DNS plugin
if ! command -v certbot &>/dev/null; then
    echo "==> Installing certbot..."
    apt-get update -qq && apt-get install -y certbot python3-pip
fi

if ! pip3 show certbot-dns-duckdns &>/dev/null 2>&1; then
    echo "==> Installing certbot DuckDNS plugin..."
    pip3 install certbot-dns-duckdns
fi

# 3. Write DuckDNS credentials file
CREDS_FILE="/etc/letsencrypt/duckdns.ini"
mkdir -p /etc/letsencrypt
cat > "$CREDS_FILE" << EOF
dns_duckdns_token = $DUCKDNS_TOKEN
EOF
chmod 600 "$CREDS_FILE"
echo "==> Saved DuckDNS credentials to $CREDS_FILE"

# 4. Obtain certificate via DNS challenge (no web server needed)
echo "==> Requesting Let's Encrypt certificate via DNS challenge..."
certbot certonly \
    --authenticator dns-duckdns \
    --dns-duckdns-credentials "$CREDS_FILE" \
    --dns-duckdns-propagation-seconds 60 \
    --domain "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "admin@duckdns.org" \
    --no-eff-email

echo "==> Certificate obtained!"

# 5. Inject domain into nginx configs
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$NGINX_CONF"
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$NGINX_INIT_CONF"
echo "==> Updated nginx configs with domain: $DOMAIN"

# 6. Create certbot webroot directory (used only for renewals via nginx)
mkdir -p "$CERTBOT_WEBROOT"

# 7. Start nginx with the full HTTPS config
cd "$PROJECT_DIR"
docker compose up -d nginx
echo "==> Nginx started with HTTPS"

echo ""
echo "✓ Done! API is now available at: https://$DOMAIN"
echo ""
echo "==> ACTION REQUIRED — Update Vercel:"
echo "    Go to: Vercel → your project → Settings → Environment Variables"
echo "    Set:  NEXT_PUBLIC_API_URL = https://$DOMAIN"
echo "    Then redeploy the frontend."
echo ""
echo "==> Auto-renewal cron (run: crontab -e as root):"
echo "    0 3 * * * certbot renew --quiet --dns-duckdns-credentials $CREDS_FILE && docker compose -f $PROJECT_DIR/docker-compose.yml exec nginx nginx -s reload"
