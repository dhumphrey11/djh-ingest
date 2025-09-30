#!/bin/bash

# Create Google Cloud Scheduler jobs for the ingestion pipeline
# This script creates all scheduled jobs that trigger the orchestrator service

set -e

# Configuration
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"djh-app-3bdc2"}
REGION=${REGION:-"us-central1"}
ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-"https://orchestrator-service-mu5ahraz3a-uc.a.run.app"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Creating Cloud Scheduler jobs for stock ingestion pipeline${NC}"
echo "Project: $PROJECT_ID"
echo "Region: $REGION" 
echo "Orchestrator URL: $ORCHESTRATOR_URL"
echo ""

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${RED}Error: No active gcloud authentication found${NC}"
    echo "Run: gcloud auth login"
    exit 1
fi

# Enable required APIs
echo -e "${YELLOW}Enabling required APIs...${NC}"
gcloud services enable cloudscheduler.googleapis.com --project="$PROJECT_ID"

# Create scheduler service account if it doesn't exist
SCHEDULER_SA="scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SCHEDULER_SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo -e "${YELLOW}Creating scheduler service account...${NC}"
    gcloud iam service-accounts create scheduler-invoker \
        --display-name="Cloud Scheduler Service Account" \
        --description="Service account for Cloud Scheduler to invoke Cloud Run services" \
        --project="$PROJECT_ID"
    
    # Grant Cloud Run Invoker role to the service account
    gcloud run services add-iam-policy-binding orchestrator-service \
        --member="serviceAccount:${SCHEDULER_SA}" \
        --role="roles/run.invoker" \
        --region="$REGION" \
        --project="$PROJECT_ID"
    
    echo -e "${GREEN}✓ Scheduler service account created and configured${NC}"
else
    echo -e "${GREEN}✓ Scheduler service account already exists${NC}"
fi

# Function to create a Cloud Scheduler job
create_job() {
    local job_name="$1"
    local schedule="$2"
    local url_path="$3" 
    local scope="$4"
    local description="$5"
    
    local full_url="${ORCHESTRATOR_URL}${url_path}"
    local payload="{\"scope\": \"${scope}\", \"job\": \"${job_name}\"}"
    
    echo -e "${YELLOW}Creating job: $job_name${NC}"
    
    # Delete existing job if it exists
    gcloud scheduler jobs delete "$job_name" \
        --location="$REGION" \
        --quiet 2>/dev/null || true
    
    # Create the job with OIDC authentication
    gcloud scheduler jobs create http "$job_name" \
        --location="$REGION" \
        --schedule="$schedule" \
        --uri="$full_url" \
        --http-method=POST \
        --headers="Content-Type=application/json" \
        --message-body="$payload" \
        --description="$description" \
        --time-zone="America/New_York" \
        --oidc-service-account-email="scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
        --oidc-token-audience="$full_url"
    
    echo -e "${GREEN}✓ Created: $job_name${NC}"
    echo ""
}

echo -e "${YELLOW}Creating Tiingo jobs...${NC}"

# Tiingo daily prices - After market close (6 PM ET)
create_job \
    "tiingo-daily-prices" \
    "0 18 * * 1-5" \
    "/tiingo/daily-prices" \
    "entire_watchlist" \
    "Fetch EOD daily prices for entire watchlist from Tiingo"

# Tiingo indices - After market close (6 PM ET) 
create_job \
    "tiingo-daily-prices-indices" \
    "5 18 * * 1-5" \
    "/tiingo/daily-prices-indices" \
    "indices" \
    "Fetch EOD daily prices for market indices from Tiingo"

echo -e "${YELLOW}Creating Finnhub jobs...${NC}"

# Finnhub intraday quotes - Every 5 minutes during market hours (9:30 AM - 4 PM ET)
create_job \
    "finnhub-quote-portfolio" \
    "*/5 9-16 * * 1-5" \
    "/finnhub/quote-portfolio" \
    "active_symbols" \
    "Fetch intraday quotes for active portfolio symbols from Finnhub"

# Finnhub indices quotes - Every 5 minutes during market hours
create_job \
    "finnhub-quote-indices" \
    "*/5 9-16 * * 1-5" \
    "/finnhub/quote-indices" \
    "indices" \
    "Fetch intraday quotes for market indices from Finnhub"

# Finnhub company news for universe - Every 2 hours during business hours
create_job \
    "finnhub-company-news-universe" \
    "0 8,10,12,14,16,18 * * 1-5" \
    "/finnhub/company-news-universe" \
    "entire_watchlist" \
    "Fetch company news for entire watchlist from Finnhub"

# Finnhub company news for portfolio - Every hour during business hours  
create_job \
    "finnhub-company-news-portfolio" \
    "0 8,9,10,11,12,13,14,15,16,17,18 * * 1-5" \
    "/finnhub/company-news-portfolio" \
    "active_symbols" \
    "Fetch company news for active portfolio symbols from Finnhub"

# Finnhub fundamentals and earnings - Daily at 7 AM ET
create_job \
    "finnhub-fundamentals-earnings" \
    "0 7 * * 1-5" \
    "/finnhub/fundamentals-earnings" \
    "entire_watchlist" \
    "Fetch fundamentals and earnings data from Finnhub"

echo -e "${YELLOW}Creating Polygon jobs...${NC}"

# Polygon news for universe - Every 3 hours during business hours
create_job \
    "polygon-news-universe" \
    "0 8,11,14,17 * * 1-5" \
    "/polygon/news-universe" \
    "entire_watchlist" \
    "Fetch company news for entire watchlist from Polygon"

# Polygon news for portfolio - Every hour during business hours
create_job \
    "polygon-news-portfolio" \
    "0 8,9,10,11,12,13,14,15,16,17,18 * * 1-5" \
    "/polygon/news-portfolio" \
    "active_symbols" \
    "Fetch company news for active portfolio symbols from Polygon"

# Polygon market news - Every 30 minutes during business hours
create_job \
    "polygon-news-market" \
    "0,30 8-18 * * 1-5" \
    "/polygon/news-market" \
    "none" \
    "Fetch market-wide news articles from Polygon"

echo -e "${YELLOW}Creating AlphaVantage jobs...${NC}"

# AlphaVantage technical indicators - Daily at 5 PM ET (after market close)
create_job \
    "alpha-vantage-technical-indicators" \
    "0 17 * * 1-5" \
    "/alphavantage/technical-indicators" \
    "entire_watchlist" \
    "Fetch technical indicators for entire watchlist from AlphaVantage"

echo -e "${GREEN}All Cloud Scheduler jobs created successfully!${NC}"
echo ""

# List all jobs
echo -e "${YELLOW}Created jobs:${NC}"
gcloud scheduler jobs list --location="$REGION" --format="table(name,schedule,state)"

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo "Jobs are configured to run in Eastern Time (America/New_York)"
echo ""
echo "Schedule summary:"
echo "• Tiingo: Daily after market close (6:00 PM ET)"
echo "• Finnhub quotes: Every 5 minutes during market hours"
echo "• Finnhub news: Every 1-2 hours during business hours"
echo "• Finnhub fundamentals: Daily at 7:00 AM ET"
echo "• Polygon news: Every 0.5-3 hours during business hours"
echo "• AlphaVantage indicators: Daily at 5:00 PM ET"
echo ""
echo "To manually trigger a job:"
echo "gcloud scheduler jobs run JOB_NAME --location=$REGION"
echo ""
echo "To view job history:"
echo "gcloud scheduler jobs describe JOB_NAME --location=$REGION"