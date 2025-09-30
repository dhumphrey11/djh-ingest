#!/bin/bash

# Final deployment readiness check
# Run this script before deployment to ensure everything is ready

set -e

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"djh-app-3bdc2"}
REGION=${REGION:-"us-central1"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 DEPLOYMENT READINESS CHECK${NC}"
echo "============================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Track if we're ready to deploy
READY=true

# 1. Check authentication
echo -e "${BLUE}1. Checking Google Cloud authentication...${NC}"
if gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
    echo -e "   ✅ Authenticated as: $ACCOUNT"
else
    echo -e "   ❌ Not authenticated to Google Cloud"
    echo "      Run: gcloud auth login"
    READY=false
fi

# 2. Check project configuration
echo -e "${BLUE}2. Checking project configuration...${NC}"
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "$CURRENT_PROJECT" = "$PROJECT_ID" ]; then
    echo -e "   ✅ Project set to: $PROJECT_ID"
else
    echo -e "   ❌ Project mismatch. Expected: $PROJECT_ID, Got: $CURRENT_PROJECT"
    echo "      Run: gcloud config set project $PROJECT_ID"
    READY=false
fi

# 3. Check required APIs
echo -e "${BLUE}3. Checking required APIs...${NC}"
REQUIRED_APIS=("cloudbuild.googleapis.com" "run.googleapis.com" "cloudscheduler.googleapis.com" "firestore.googleapis.com" "secretmanager.googleapis.com")
for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:$api" --format="value(name)" | grep -q "$api"; then
        echo -e "   ✅ $api enabled"
    else
        echo -e "   ❌ $api not enabled"
        echo "      Run: gcloud services enable $api"
        READY=false
    fi
done

# 4. Check API secrets
echo -e "${BLUE}4. Checking API secrets in Secret Manager...${NC}"
REQUIRED_SECRETS=("TIINGO_API_KEY" "FINNHUB_API_KEY" "POLYGON_API_KEY" "ALPHAVANTAGE_API_KEY")
for secret in "${REQUIRED_SECRETS[@]}"; do
    if gcloud secrets list --filter="name:$secret" --format="value(name)" | grep -q "$secret"; then
        echo -e "   ✅ $secret configured"
    else
        echo -e "   ❌ $secret not found"
        echo "      Run: echo 'your-api-key' | gcloud secrets create $secret --data-file=-"
        READY=false
    fi
done

# 5. Check Firestore database
echo -e "${BLUE}5. Checking Firestore database...${NC}"
if gcloud firestore databases list --format="value(name)" | grep -q "projects/$PROJECT_ID/databases/(default)"; then
    echo -e "   ✅ Firestore database exists"
    
    # Check if configuration documents exist
    if gcloud firestore documents describe --collection=config --document=watchlist >/dev/null 2>&1; then
        echo -e "   ✅ Watchlist configuration exists"
    else
        echo -e "   ⚠️  Watchlist configuration missing"
        echo "      Run: ./infra/init_firestore.sh"
    fi
else
    echo -e "   ❌ Firestore database not found"
    echo "      Run: gcloud firestore databases create --region=$REGION"
    READY=false
fi

# 6. Check file structure
echo -e "${BLUE}6. Checking file structure...${NC}"
REQUIRED_FILES=(
    "shared/models.py"
    "shared/utils/retries.py"
    "shared/utils/env.py"
    "services/tiingo-service/app.py"
    "services/tiingo-service/Dockerfile"
    "services/finnhub-service/app.py"
    "services/finnhub-service/Dockerfile"
    "services/polygon-service/app.py"
    "services/polygon-service/Dockerfile"
    "services/alphavantage-service/app.py"
    "services/alphavantage-service/Dockerfile"
    "orchestrator/app.py"
    "orchestrator/Dockerfile"
    "infra/deploy_all.sh"
    "infra/create_schedulers.sh"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "   ✅ $file exists"
    else
        echo -e "   ❌ $file missing"
        READY=false
    fi
done

# 7. Check script permissions
echo -e "${BLUE}7. Checking script permissions...${NC}"
SCRIPTS=("infra/deploy_all.sh" "infra/create_schedulers.sh" "infra/init_firestore.sh")
for script in "${SCRIPTS[@]}"; do
    if [ -x "$script" ]; then
        echo -e "   ✅ $script executable"
    else
        echo -e "   ❌ $script not executable"
        echo "      Run: chmod +x $script"
        READY=false
    fi
done

# 8. Check for Python syntax errors
echo -e "${BLUE}8. Checking Python syntax...${NC}"
if find . -name "*.py" -exec python3 -m py_compile {} \; 2>/dev/null; then
    echo -e "   ✅ All Python files compile successfully"
else
    echo -e "   ❌ Python syntax errors found"
    READY=false
fi

echo ""
echo "============================================"

if [ "$READY" = true ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT!${NC}"
    echo ""
    echo "🚀 Next steps:"
    echo "1. Initialize Firestore configuration (if needed):"
    echo "   ./infra/init_firestore.sh"
    echo ""
    echo "2. Deploy all services:"
    echo "   ./infra/deploy_all.sh"
    echo ""
    echo "3. Create Cloud Scheduler jobs:"
    echo "   export ORCHESTRATOR_URL=<orchestrator-url-from-step-2>"
    echo "   ./infra/create_schedulers.sh"
    echo ""
else
    echo -e "${RED}❌ DEPLOYMENT NOT READY - FIX ISSUES ABOVE${NC}"
    echo ""
    echo "Address the issues marked with ❌ and run this script again."
    exit 1
fi