#!/usr/bin/env bash
# setup-ssl.sh — Obtain a Let's Encrypt certificate and configure Nginx HTTPS.
#
# Prerequisites:
#   1. A domain pointing to this server's IP (DNS A record).
#   2. Ports 80 and 443 open on the firewall.
#   3. Docker and Docker Compose installed.
#
# Usage:
#   chmod +x scripts/setup-ssl.sh
#   sudo ./scripts/setup-ssl.sh api.yourdomain.com

set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "Usage: $0 <your-domain>"
    echo "Example: $0 api.dimenfy.com"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_CONF="$PROJECT_DIR/nginx/nginx.conf"
NGINX_INIT_CONF="$PROJECT_DIR/nginx/nginx-init.conf"
CERTBOT_WEBROOT="$PROJECT_DIR/nginx/certbot-webroot"

echo "==> Setting up HTTPS for domain: $DOMAIN"

# 1. Install certbot if missing
if ! command -v certbot &>/dev/null; then
    echo "==> Installing certbot..."
    apt-get update -qq && apt-get install -y certbot
fi

# 2. Replace YOUR_DOMAIN placeholder in both nginx configs
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$NGINX_CONF"
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$NGINX_INIT_CONF"
echo "==> Updated nginx configs with domain: $DOMAIN"

# 3. Create certbot webroot directory
mkdir -p "$CERTBOT_WEBROOT"

# 4. Temporarily use HTTP-only nginx config to allow ACME challenge
cp "$NGINX_CONF" "$NGINX_CONF.backup"
cp "$NGINX_INIT_CONF" "$NGINX_CONF"

# 5. Start (or restart) nginx with the HTTP-only config
cd "$PROJECT_DIR"
docker compose up -d nginx
echo "==> Nginx started (HTTP-only mode)"
sleep 3

# 6. Obtain the certificate using webroot challenge
echo "==> Requesting Let's Encrypt certificate..."
certbot certonly \
    --webroot \
    --webroot-path "$CERTBOT_WEBROOT" \
    --domain "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "admin@$DOMAIN" \
    --no-eff-email

# 7. Restore full HTTPS nginx config
cp "$NGINX_CONF.backup" "$NGINX_CONF"
rm "$NGINX_CONF.backup"
echo "==> Restored full HTTPS nginx config"

# 8. Reload nginx with HTTPS config
docker compose exec nginx nginx -s reload
echo ""
echo "✓ HTTPS is now active at https://$DOMAIN"
echo ""
echo "==> Next step: set NEXT_PUBLIC_API_URL=https://$DOMAIN in Vercel."
echo ""
echo "==> To auto-renew the certificate, add this to root's crontab (crontab -e):"
echo "    0 3 * * * certbot renew --quiet && docker compose -f $PROJECT_DIR/docker-compose.yml exec nginx nginx -s reload"
