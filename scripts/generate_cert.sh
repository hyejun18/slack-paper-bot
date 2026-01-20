#!/bin/bash
#
# Generate self-signed SSL certificate for Slack Paper Bot
#
# Usage: ./generate_cert.sh [IP_ADDRESS]
#
# This script creates a self-signed certificate valid for 365 days.
# Note: Slack Event API may not accept self-signed certificates directly.
# Consider using Cloudflare Tunnel or ngrok for production.

set -e

# Configuration
CERT_DIR="../certs"
CERT_FILE="$CERT_DIR/cert.pem"
KEY_FILE="$CERT_DIR/key.pem"
DAYS_VALID=365

# Get IP address (use argument or try to detect)
if [ -n "$1" ]; then
    IP_ADDRESS="$1"
else
    # Try to get public IP
    IP_ADDRESS=$(curl -s https://ifconfig.me 2>/dev/null || curl -s https://api.ipify.org 2>/dev/null || echo "127.0.0.1")
fi

echo "========================================"
echo "  Self-Signed Certificate Generator"
echo "========================================"
echo ""
echo "IP Address: $IP_ADDRESS"
echo "Output directory: $CERT_DIR"
echo ""

# Create certs directory
mkdir -p "$CERT_DIR"

# Generate certificate with SAN (Subject Alternative Name)
echo "Generating certificate..."

openssl req -x509 \
    -newkey rsa:4096 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -sha256 \
    -days "$DAYS_VALID" \
    -nodes \
    -subj "/C=KR/ST=Seoul/L=Seoul/O=SlackPaperBot/OU=Development/CN=$IP_ADDRESS" \
    -addext "subjectAltName=IP:$IP_ADDRESS,IP:127.0.0.1,DNS:localhost"

# Set permissions
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo ""
echo "========================================"
echo "  Certificate Generated Successfully!"
echo "========================================"
echo ""
echo "Files created:"
echo "  Certificate: $CERT_FILE"
echo "  Private Key: $KEY_FILE"
echo ""
echo "Certificate details:"
openssl x509 -in "$CERT_FILE" -noout -subject -dates
echo ""
echo "========================================"
echo "  IMPORTANT NOTES"
echo "========================================"
echo ""
echo "1. Self-signed certificates may NOT work with Slack Event API directly."
echo "   Slack requires valid SSL certificates for webhook URLs."
echo ""
echo "2. Recommended alternatives:"
echo ""
echo "   A) Use ngrok (easiest for development):"
echo "      ngrok http 8000"
echo "      Then use the ngrok HTTPS URL for Slack Event Subscriptions"
echo ""
echo "   B) Use Cloudflare Tunnel (free, production-ready):"
echo "      cloudflared tunnel --url http://localhost:8000"
echo ""
echo "   C) Get a free domain and use Let's Encrypt:"
echo "      - Get a free domain from freenom.com or duckdns.org"
echo "      - Use certbot to get a free SSL certificate"
echo ""
echo "3. For development/testing, you can run without SSL:"
echo "   Set 'ssl.enabled: false' in config.yml"
echo "   Use ngrok or Cloudflare Tunnel to expose HTTP locally"
echo ""
