#!/bin/bash
# Deploy GCP pipeline components
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - GCP project set: gcloud config set project YOUR_PROJECT
#   - APIs enabled: Cloud Run, Cloud Scheduler, Artifact Registry
#
# Usage:
#   ./gcp/deploy.sh [premarket|monitor|weekend|all]

set -euo pipefail

PROJECT_ID=$(gcloud config get-value project)
REGION="us-east1"
IMAGE="us-east1-docker.pkg.dev/${PROJECT_ID}/trading/trading-system"

echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"

# Build and push Docker image
build_image() {
    echo "Building Docker image..."
    gcloud builds submit --tag "${IMAGE}" .
}

# Deploy pre-market brief (Cloud Run Job)
deploy_premarket() {
    echo "Deploying pre-market brief job..."
    gcloud run jobs create premarket-brief \
        --image "${IMAGE}" \
        --region "${REGION}" \
        --memory 1Gi \
        --cpu 1 \
        --max-retries 1 \
        --command python,-m,gcp.premarket_brief \
        --set-env-vars "DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update premarket-brief \
        --image "${IMAGE}" \
        --region "${REGION}" \
        --command python,-m,gcp.premarket_brief \
        --set-env-vars "DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}" \
        --quiet

    # Schedule: 8:30 AM ET weekdays (13:30 UTC)
    gcloud scheduler jobs create http premarket-trigger \
        --location "${REGION}" \
        --schedule "30 13 * * 1-5" \
        --time-zone "America/New_York" \
        --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/premarket-brief:run" \
        --http-method POST \
        --oauth-service-account-email "${PROJECT_ID}@appspot.gserviceaccount.com" \
        --quiet 2>/dev/null || echo "Scheduler job already exists"
}

# Deploy signal monitor (Cloud Run Service)
deploy_monitor() {
    echo "Deploying signal monitor service..."
    gcloud run deploy signal-monitor \
        --image "${IMAGE}" \
        --region "${REGION}" \
        --memory 2Gi \
        --cpu 1 \
        --min-instances 0 \
        --max-instances 1 \
        --concurrency 1 \
        --command python,-m,gcp.signal_monitor \
        --set-env-vars "DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}" \
        --no-allow-unauthenticated \
        --quiet
}

# Deploy weekend review (Cloud Run Job)
deploy_weekend() {
    echo "Deploying weekend review job..."
    gcloud run jobs create weekend-review \
        --image "${IMAGE}" \
        --region "${REGION}" \
        --memory 1Gi \
        --cpu 1 \
        --max-retries 1 \
        --command python,-m,gcp.weekend_review \
        --set-env-vars "DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update weekend-review \
        --image "${IMAGE}" \
        --region "${REGION}" \
        --command python,-m,gcp.weekend_review \
        --set-env-vars "DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}" \
        --quiet

    # Schedule: Saturday 9 AM ET (14:00 UTC)
    gcloud scheduler jobs create http weekend-trigger \
        --location "${REGION}" \
        --schedule "0 14 * * 6" \
        --time-zone "America/New_York" \
        --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/weekend-review:run" \
        --http-method POST \
        --oauth-service-account-email "${PROJECT_ID}@appspot.gserviceaccount.com" \
        --quiet 2>/dev/null || echo "Scheduler job already exists"
}

case "${1:-all}" in
    premarket) build_image && deploy_premarket ;;
    monitor)   build_image && deploy_monitor ;;
    weekend)   build_image && deploy_weekend ;;
    all)
        build_image
        deploy_premarket
        deploy_monitor
        deploy_weekend
        echo "All components deployed."
        ;;
    *)
        echo "Usage: $0 [premarket|monitor|weekend|all]"
        exit 1
        ;;
esac
