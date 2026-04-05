#!/usr/bin/env bash
# Usage: ./deploy.sh <your-domain.com> <your@email.com>
set -euo pipefail

DOMAIN="${1:?Usage: ./deploy.sh <domain> <email>}"
EMAIL="${2:?Usage: ./deploy.sh <domain> <email>}"
REPO="https://github.com/NousResearch/hermes-agent.git"
INSTALL_DIR="/opt/hermes-control-plane"

echo "==> Installing dependencies"
apt-get update -qq
apt-get install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx git

echo "==> Cloning repo"
if [ -d "$INSTALL_DIR" ]; then
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO" "$INSTALL_DIR"
fi

echo "==> Setting up venv"
cd "$INSTALL_DIR"
python3.11 -m venv venv
venv/bin/pip install -q -r requirements.txt

echo "==> Creating systemd service"
cat > /etc/systemd/system/hermes-control-plane.service << EOF
[Unit]
Description=Hermes AI Employee Control Plane
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python scripts/control_plane.py
EnvironmentFile=$INSTALL_DIR/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hermes-control-plane

echo "==> Creating nginx config"
cat > /etc/nginx/sites-available/hermes-control-plane << EOF
server {
    listen 80;
    server_name $DOMAIN;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/hermes-control-plane /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo "==> Obtaining SSL certificate"
certbot --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive

echo "==> Starting service"
systemctl start hermes-control-plane
systemctl status hermes-control-plane

echo ""
echo "✅ Deployed! Control plane running at https://$DOMAIN"
echo "Next: copy your .env file to $INSTALL_DIR/.env and restart: systemctl restart hermes-control-plane"
