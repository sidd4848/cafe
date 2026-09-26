#!/bin/sh
# Writes /config.js from Cloud Run env vars at container start, so one image runs in any
# environment. Values are public (API URL, Firebase *web* config); no secrets belong here.
set -e
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
cat > /usr/share/nginx/html/config.js <<EOF
window.__CONFIG__ = {
  API_URL: "$(esc "$API_URL")",
  CAFE_ID: "$(esc "${CAFE_ID:-koramangala}")",
  FIREBASE_API_KEY: "$(esc "$FIREBASE_API_KEY")",
  FIREBASE_AUTH_DOMAIN: "$(esc "$FIREBASE_AUTH_DOMAIN")",
  FIREBASE_PROJECT_ID: "$(esc "$FIREBASE_PROJECT_ID")",
  FIREBASE_STORAGE_BUCKET: "$(esc "$FIREBASE_STORAGE_BUCKET")",
  FIREBASE_MESSAGING_SENDER_ID: "$(esc "$FIREBASE_MESSAGING_SENDER_ID")",
  FIREBASE_APP_ID: "$(esc "$FIREBASE_APP_ID")"
};
EOF
echo "runtime config written for API_URL=$API_URL"
