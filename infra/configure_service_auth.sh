#!/bin/bash

# Configure Cloud Run service authentication
# This script sets up proper OIDC authentication between services

set -e

PROJECT_ID="djh-app-3bdc2"
REGION="us-central1"
ORCHESTRATOR_SA="974427192502-compute@developer.gserviceaccount.com"

echo "🔐 Configuring Cloud Run service authentication..."

# List of services that need to be protected
SERVICES=("tiingo-service" "finnhub-service" "polygon-service" "alphavantage-service")

for service in "${SERVICES[@]}"; do
    echo "  🔧 Configuring $service..."
    
    # Remove --allow-unauthenticated by removing the IAM binding for allUsers
    echo "    - Requiring authentication for $service"
    gcloud run services remove-iam-policy-binding $service \
        --region=$REGION \
        --member="allUsers" \
        --role="roles/run.invoker" \
        --quiet 2>/dev/null || echo "      (no public access to remove)"
    
    # Grant the orchestrator service account permission to invoke this service
    echo "    - Granting invoke permission to orchestrator service account"
    gcloud run services add-iam-policy-binding $service \
        --region=$REGION \
        --member="serviceAccount:$ORCHESTRATOR_SA" \
        --role="roles/run.invoker" \
        --quiet
    
    echo "    ✅ $service configured"
done

echo ""
echo "🎉 All services configured for authenticated access!"
echo ""
echo "Summary:"
echo "• Services now require authentication"
echo "• Orchestrator service account ($ORCHESTRATOR_SA) can invoke all services"
echo "• OIDC tokens will be used for service-to-service communication"