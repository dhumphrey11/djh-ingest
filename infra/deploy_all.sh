#!/bin/bash

# Deploy all services to Google Cloud Run
# This script builds and deploys all microservices and the orchestrator

set -e

# Configuration
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"djh-app-3bdc2"}
REGION=${REGION:-"us-central1"}
IMAGE_TAG=${IMAGE_TAG:-"latest"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Deploying Stock Analysis Ingestion Pipeline to Cloud Run${NC}"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Image tag: $IMAGE_TAG"
echo ""

# Check if gcloud is authenticated and configured
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${RED}Error: No active gcloud authentication found${NC}"
    echo "Run: gcloud auth login"
    exit 1
fi

# Set the project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}Enabling required Google Cloud APIs...${NC}"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    firestore.googleapis.com \
    secretmanager.googleapis.com

# Function to build and deploy a service
deploy_service() {
    local service_name="$1"
    local dockerfile_dir="$2" 
    local memory="$3"
    local cpu="$4"
    local max_instances="$5"
    local timeout="$6"
    
    local image_name="us-docker.pkg.dev/${PROJECT_ID}/gcr.io/${service_name}:${IMAGE_TAG}"
    
    echo -e "${BLUE}Building and deploying ${service_name}...${NC}"
    
    # Build the Docker image using Cloud Build with temporary Dockerfile in root
    echo "Building Docker image: $image_name"
    echo "Build context: $ROOT_DIR"
    echo "Dockerfile: $dockerfile_dir/Dockerfile"
    
    # Copy Dockerfile to root temporarily (gcloud builds submit looks for Dockerfile in root)
    cp "$ROOT_DIR/$dockerfile_dir/Dockerfile" "$ROOT_DIR/Dockerfile"
    
    gcloud builds submit \
        --tag "$image_name" \
        --project "$PROJECT_ID" \
        "$ROOT_DIR"
    
    # Clean up temporary Dockerfile
    rm "$ROOT_DIR/Dockerfile"
    
    # Deploy to Cloud Run
    echo "Deploying to Cloud Run..."
    gcloud run deploy "$service_name" \
        --image "$image_name" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --memory "$memory" \
        --cpu "$cpu" \
        --max-instances "$max_instances" \
        --timeout "$timeout" \
        --no-allow-unauthenticated \
        --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_PROJECT=${PROJECT_ID},DEV_MODE=false" \
        --execution-environment gen2
    
    echo -e "${GREEN}✓ Deployed: $service_name${NC}"
    echo ""
}

# Function to build and deploy a service with API key secret
deploy_service_with_secret() {
    local service_name="$1"
    local dockerfile_dir="$2" 
    local memory="$3"
    local cpu="$4"
    local max_instances="$5"
    local timeout="$6"
    local secret_name="$7"
    local env_var_name="$8"
    
    local image_name="us-docker.pkg.dev/${PROJECT_ID}/gcr.io/${service_name}:${IMAGE_TAG}"
    
    echo -e "${BLUE}Building and deploying ${service_name} with secret ${secret_name}...${NC}"
    
    # Build the Docker image using Cloud Build with temporary Dockerfile in root
    echo "Building Docker image: $image_name"
    echo "Build context: $ROOT_DIR"
    echo "Dockerfile: $dockerfile_dir/Dockerfile"
    
    # Copy Dockerfile to root temporarily (gcloud builds submit looks for Dockerfile in root)
    cp "$ROOT_DIR/$dockerfile_dir/Dockerfile" "$ROOT_DIR/Dockerfile"
    
    gcloud builds submit \
        --tag "$image_name" \
        --project "$PROJECT_ID" \
        "$ROOT_DIR"
    
    # Clean up temporary Dockerfile
    rm "$ROOT_DIR/Dockerfile"
    
    # Deploy to Cloud Run with secrets
    echo "Deploying to Cloud Run with secret..."
    gcloud run deploy "$service_name" \
        --image "$image_name" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --memory "$memory" \
        --cpu "$cpu" \
        --max-instances "$max_instances" \
        --timeout "$timeout" \
        --no-allow-unauthenticated \
        --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_PROJECT=${PROJECT_ID},DEV_MODE=false" \
        --set-secrets="${env_var_name}=${secret_name}:latest" \
        --execution-environment gen2
    
    echo -e "${GREEN}✓ Deployed: $service_name with secret $secret_name${NC}"
    echo ""
}

# Get the root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}Deploying microservices...${NC}"

# Deploy Tiingo service
deploy_service_with_secret \
    "tiingo-service" \
    "services/tiingo-service" \
    "1Gi" \
    "1" \
    "5" \
    "900s" \
    "tiingo-api-key" \
    "TIINGO_API_KEY"

# Deploy Finnhub service  
deploy_service_with_secret \
    "finnhub-service" \
    "services/finnhub-service" \
    "2Gi" \
    "2" \
    "10" \
    "900s" \
    "finnhub-api-key" \
    "FINNHUB_API_KEY"

# Deploy Polygon service
deploy_service_with_secret \
    "polygon-service" \
    "services/polygon-service" \
    "1Gi" \
    "1" \
    "5" \
    "900s" \
    "polygon-api-key" \
    "POLYGON_API_KEY"

# Deploy AlphaVantage service
deploy_service_with_secret \
    "alphavantage-service" \
    "services/alphavantage-service" \
    "1Gi" \
    "1" \
    "3" \
    "900s" \
    "alphavantage-api-key" \
    "ALPHAVANTAGE_API_KEY"

echo -e "${YELLOW}Deploying orchestrator...${NC}"

# Deploy Orchestrator service
deploy_service \
    "orchestrator-service" \
    "orchestrator" \
    "2Gi" \
    "2" \
    "10" \
    "900s"

# Get service URLs for configuration
echo -e "${YELLOW}Getting service URLs...${NC}"
TIINGO_URL=$(gcloud run services describe tiingo-service --region=$REGION --format="value(status.url)")
FINNHUB_URL=$(gcloud run services describe finnhub-service --region=$REGION --format="value(status.url)")
POLYGON_URL=$(gcloud run services describe polygon-service --region=$REGION --format="value(status.url)")
ALPHAVANTAGE_URL=$(gcloud run services describe alphavantage-service --region=$REGION --format="value(status.url)")
ORCHESTRATOR_URL=$(gcloud run services describe orchestrator-service --region=$REGION --format="value(status.url)")

echo -e "${GREEN}All services deployed successfully!${NC}"
echo ""
echo "Service URLs:"
echo "• Tiingo: $TIINGO_URL"
echo "• Finnhub: $FINNHUB_URL"  
echo "• Polygon: $POLYGON_URL"
echo "• AlphaVantage: $ALPHAVANTAGE_URL"
echo "• Orchestrator: $ORCHESTRATOR_URL"
echo ""

# Update orchestrator with service URLs
echo -e "${YELLOW}Updating orchestrator with service URLs...${NC}"
gcloud run services update orchestrator-service \
    --region="$REGION" \
    --set-env-vars="TIINGO_SERVICE_URL=${TIINGO_URL},FINNHUB_SERVICE_URL=${FINNHUB_URL},POLYGON_SERVICE_URL=${POLYGON_URL},ALPHAVANTAGE_SERVICE_URL=${ALPHAVANTAGE_URL}"

echo -e "${GREEN}Orchestrator updated with service URLs${NC}"
echo ""

# Create IAM bindings for service-to-service communication
echo -e "${YELLOW}Setting up IAM for service-to-service communication...${NC}"

# Get the orchestrator service account
ORCHESTRATOR_SA=$(gcloud run services describe orchestrator-service \
    --region=$REGION \
    --format="value(spec.template.spec.serviceAccountName)")

if [ -z "$ORCHESTRATOR_SA" ]; then
    ORCHESTRATOR_SA="${PROJECT_ID}@appspot.gserviceaccount.com"
fi

# Grant orchestrator permission to invoke other services
for service in tiingo-service finnhub-service polygon-service alphavantage-service; do
    gcloud run services add-iam-policy-binding $service \
        --region=$REGION \
        --member="serviceAccount:${ORCHESTRATOR_SA}" \
        --role="roles/run.invoker"
    echo "✓ Granted orchestrator access to $service"
done

echo ""
echo -e "${GREEN}Service-to-service IAM configured${NC}"

# Store configuration in a file for Cloud Scheduler setup
cat > "${ROOT_DIR}/deployment-config.env" << EOF
# Deployment Configuration
PROJECT_ID=$PROJECT_ID
REGION=$REGION
ORCHESTRATOR_URL=$ORCHESTRATOR_URL
TIINGO_SERVICE_URL=$TIINGO_URL
FINNHUB_SERVICE_URL=$FINNHUB_URL
POLYGON_SERVICE_URL=$POLYGON_URL
ALPHAVANTAGE_SERVICE_URL=$ALPHAVANTAGE_URL
EOF

echo -e "${GREEN}Configuration saved to deployment-config.env${NC}"
echo ""

# Provide next steps
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Set up API keys in Google Secret Manager:"
echo "   • TIINGO_API_KEY"
echo "   • FINNHUB_API_KEY" 
echo "   • POLYGON_API_KEY"
echo "   • ALPHAVANTAGE_API_KEY"
echo ""
echo "2. Initialize Firestore database and collections"
echo ""
echo "3. Create Cloud Scheduler jobs:"
echo "   export ORCHESTRATOR_URL=$ORCHESTRATOR_URL"
echo "   ./infra/create_schedulers.sh"
echo ""
echo "4. Test the deployment:"
echo "   curl -X GET $ORCHESTRATOR_URL/health"
echo ""
echo -e "${GREEN}Deployment complete!${NC}"