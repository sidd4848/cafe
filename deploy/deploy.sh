#!/usr/bin/env bash
# Build and deploy Cafe Companion: two Cloud Run services, no load balancer.
#
#   cafe-api  FastAPI backend   (runs as the existing screener@ service account)
#   cafe-web  nginx + React SPA (no GCP permissions needed)
#
# Idempotent: re-run to ship a new version. Firestore rules/indexes/TTL and the seed are
# separate one-time steps (see README).
set -euo pipefail

PROJECT=stockscreenerai-6f441
REGION=asia-south1
REPO=cafe
API_SA=screener@${PROJECT}.iam.gserviceaccount.com
MANAGERS=${BOOTSTRAP_MANAGERS:-ranjansiddharth484848@gmail.com}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TAG=$(date +%Y%m%d-%H%M%S)
REG=${REGION}-docker.pkg.dev/${PROJECT}/${REPO}
G="--project=${PROJECT}"

echo "==> Artifact Registry repo"
gcloud artifacts repositories describe "$REPO" --location="$REGION" $G >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" $G \
    --description="Cafe Companion images"

echo "==> Build + deploy cafe-api"
gcloud builds submit "$ROOT/backend" --tag "$REG/cafe-api:$TAG" $G --region="$REGION" --quiet
gcloud run deploy cafe-api --image "$REG/cafe-api:$TAG" --region "$REGION" $G \
  --service-account "$API_SA" --allow-unauthenticated \
  --cpu 1 --memory 512Mi --concurrency 40 --min-instances 0 --max-instances 5 --timeout 60 \
  --update-env-vars "^;^GOOGLE_CLOUD_PROJECT=${PROJECT};FIREBASE_PROJECT_ID=${PROJECT};FIRESTORE_DB=cafedata;GEMINI_MODEL=gemini-3.5-flash-lite;GEMINI_LOCATION=global;BOOTSTRAP_MANAGERS=${MANAGERS};SCHEDULER_SA=${API_SA}" \
  --quiet
API_URL=$(gcloud run services describe cafe-api --region "$REGION" $G --format='value(status.url)')
echo "    $API_URL"

echo "==> Build + deploy cafe-web"
# Firebase *web* config is public by design; read it from frontend/.env.
set -a; . "$ROOT/frontend/.env"; set +a
gcloud builds submit "$ROOT/frontend" --tag "$REG/cafe-web:$TAG" $G --region="$REGION" --quiet
gcloud run deploy cafe-web --image "$REG/cafe-web:$TAG" --region "$REGION" $G \
  --allow-unauthenticated --cpu 1 --memory 256Mi --min-instances 0 --max-instances 3 \
  --update-env-vars "^;^API_URL=${API_URL};CAFE_ID=${VITE_CAFE_ID:-koramangala};FIREBASE_API_KEY=${VITE_FIREBASE_API_KEY};FIREBASE_AUTH_DOMAIN=${VITE_FIREBASE_AUTH_DOMAIN};FIREBASE_PROJECT_ID=${VITE_FIREBASE_PROJECT_ID};FIREBASE_STORAGE_BUCKET=${VITE_FIREBASE_STORAGE_BUCKET};FIREBASE_MESSAGING_SENDER_ID=${VITE_FIREBASE_MESSAGING_SENDER_ID};FIREBASE_APP_ID=${VITE_FIREBASE_APP_ID}" \
  --quiet
WEB_URL=$(gcloud run services describe cafe-web --region "$REGION" $G --format='value(status.url)')
WEB_URL2=$(gcloud run services describe cafe-web --region "$REGION" $G --format='value(metadata.annotations."run.googleapis.com/urls")' | python -c "import json,sys; u=[x for x in json.loads(sys.stdin.read() or '[]') if x != sys.argv[1]]; print(u[0] if u else sys.argv[1])" "$WEB_URL")
echo "    $WEB_URL (also $WEB_URL2)"

echo "==> Point the API at the web origin (CORS) and its own URL (scheduler audience)"
gcloud run services update cafe-api --region "$REGION" $G --quiet \
  --update-env-vars "^;^ALLOWED_ORIGINS=${WEB_URL},${WEB_URL2},http://localhost:5173;INTERNAL_AUDIENCE=${API_URL};WEB_URL=${WEB_URL}"

echo "==> Firebase Auth authorized domain"
WEB_HOST=${WEB_URL#https://}
TOKEN=$(gcloud auth print-access-token)
CFG="https://identitytoolkit.googleapis.com/admin/v2/projects/${PROJECT}/config"
DOMAINS=$(curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT" "$CFG" \
  | python -c "import json,sys; d=json.load(sys.stdin)['authorizedDomains']; h=sys.argv[1]; print(json.dumps(d if h in d else d+[h]))" "$WEB_HOST")
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json" \
  "$CFG?updateMask=authorizedDomains" -d "{\"authorizedDomains\": $DOMAINS}" >/dev/null
echo "    authorized: $DOMAINS"

echo "==> Cloud Scheduler jobs"
job() {  # name schedule path
  if gcloud scheduler jobs describe "$1" --location "$REGION" $G >/dev/null 2>&1; then verb=update; else verb=create; fi
  gcloud scheduler jobs $verb http "$1" --location "$REGION" $G --schedule "$2" --time-zone "Asia/Kolkata" \
    --uri "${API_URL}$3" --http-method POST \
    --oidc-service-account-email "$API_SA" --oidc-token-audience "$API_URL" --quiet >/dev/null
  echo "    $1 ($2)"
}
job cafe-sweep "* * * * *" /internal/jobs/sweep
job cafe-busyness "30 3 * * *" /internal/jobs/busyness

echo
echo "Done."
echo "  Web: $WEB_URL"
echo "  API: $API_URL"
