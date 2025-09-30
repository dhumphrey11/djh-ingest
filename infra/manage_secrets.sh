#!/bin/bash

# API Key Secret Management Script for GCP Secret Manager
# This script helps manage API keys stored as secrets in Google Cloud Secret Manager

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Set project ID
PROJECT_ID="djh-app-3bdc2"

# Define available API key secrets - using arrays for bash 3.x compatibility
SERVICES=("tiingo" "finnhub" "polygon" "alphavantage")
SECRET_NAMES=("tiingo-api-key" "finnhub-api-key" "polygon-api-key" "alphavantage-api-key")

# Function to get secret name for service
get_secret_name() {
    local service="$1"
    for i in "${!SERVICES[@]}"; do
        if [ "${SERVICES[$i]}" = "$service" ]; then
            echo "${SECRET_NAMES[$i]}"
            return 0
        fi
    done
    return 1
}

# Function to display usage
usage() {
    echo -e "${BLUE}API Key Secret Manager${NC}"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  list                    - List all API key secrets and their versions"
    echo "  update [service] [key]  - Update an API key secret"
    echo "  view [service]          - View the current value of an API key secret"
    echo "  help                    - Show this help message"
    echo ""
    echo "Services:"
    echo "  tiingo      - Tiingo API key"
    echo "  finnhub     - Finnhub API key"
    echo "  polygon     - Polygon API key"
    echo "  alphavantage - AlphaVantage API key"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 update tiingo your-actual-api-key-here"
    echo "  $0 view finnhub"
}

# Function to list all secrets
list_secrets() {
    echo -e "${BLUE}Current API Key Secrets:${NC}"
    echo ""
    
    for i in "${!SERVICES[@]}"; do
        service="${SERVICES[$i]}"
        secret_name="${SECRET_NAMES[$i]}"
        echo -e "${YELLOW}Service: $service${NC}"
        echo "Secret Name: $secret_name"
        
        # Get latest version info
        latest_version=$(gcloud secrets versions list "$secret_name" \
            --project="$PROJECT_ID" \
            --filter="state:enabled" \
            --limit=1 \
            --format="value(name)" 2>/dev/null)
        
        if [ -n "$latest_version" ]; then
            echo "Latest Version: $latest_version"
            
            # Get creation time
            creation_time=$(gcloud secrets versions describe "$latest_version" \
                --secret="$secret_name" \
                --project="$PROJECT_ID" \
                --format="value(createTime)" 2>/dev/null)
            echo "Created: $creation_time"
        else
            echo -e "${RED}No versions found${NC}"
        fi
        echo ""
    done
}

# Function to update a secret
update_secret() {
    local service="$1"
    local api_key="$2"
    
    if [ -z "$service" ] || [ -z "$api_key" ]; then
        echo -e "${RED}Error: Service name and API key are required${NC}"
        echo "Usage: $0 update [service] [api_key]"
        return 1
    fi
    
    local secret_name
    secret_name=$(get_secret_name "$service")
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Unknown service '$service'${NC}"
        echo "Available services: ${SERVICES[*]}"
        return 1
    fi
    
    echo -e "${BLUE}Updating $service API key...${NC}"
    
    # Create new secret version
    echo "$api_key" | gcloud secrets versions add "$secret_name" \
        --project="$PROJECT_ID" \
        --data-file=-
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully updated $service API key${NC}"
        
        # Get the new version number
        new_version=$(gcloud secrets versions list "$secret_name" \
            --project="$PROJECT_ID" \
            --filter="state:enabled" \
            --limit=1 \
            --format="value(name)")
        echo "New version: $new_version"
    else
        echo -e "${RED}✗ Failed to update $service API key${NC}"
        return 1
    fi
}

# Function to view a secret (masked for security)
view_secret() {
    local service="$1"
    
    if [ -z "$service" ]; then
        echo -e "${RED}Error: Service name is required${NC}"
        echo "Usage: $0 view [service]"
        return 1
    fi
    
    local secret_name
    secret_name=$(get_secret_name "$service")
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Unknown service '$service'${NC}"
        echo "Available services: ${SERVICES[*]}"
        return 1
    fi
    
    echo -e "${BLUE}Current $service API key:${NC}"
    
    # Get the secret value and mask most of it
    secret_value=$(gcloud secrets versions access latest \
        --secret="$secret_name" \
        --project="$PROJECT_ID" 2>/dev/null)
    
    if [ -n "$secret_value" ]; then
        # Show first 4 and last 4 characters, mask the middle
        if [ ${#secret_value} -gt 8 ]; then
            prefix="${secret_value:0:4}"
            suffix="${secret_value: -4}"
            middle_length=$((${#secret_value} - 8))
            middle=$(printf '%*s' "$middle_length" | tr ' ' '*')
            echo "$prefix$middle$suffix"
        else
            # For short keys, just show asterisks
            echo "$(printf '%*s' "${#secret_value}" | tr ' ' '*')"
        fi
        
        # Show version info
        latest_version=$(gcloud secrets versions list "$secret_name" \
            --project="$PROJECT_ID" \
            --filter="state:enabled" \
            --limit=1 \
            --format="value(name)")
        echo "Version: $latest_version"
    else
        echo -e "${RED}No secret value found${NC}"
        return 1
    fi
}

# Function to redeploy services after API key updates
redeploy_services() {
    echo -e "${YELLOW}Redeploying services to pick up new API keys...${NC}"
    
    # Get the script directory 
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Run the deployment script
    "$SCRIPT_DIR/deploy_all.sh"
}

# Main script logic
case "$1" in
    "list")
        list_secrets
        ;;
    "update")
        update_secret "$2" "$3"
        
        # Ask if user wants to redeploy services
        echo ""
        read -p "Would you like to redeploy the services to pick up the new API key? (y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            redeploy_services
        else
            echo -e "${YELLOW}Note: Services will need to be redeployed to use the new API key${NC}"
        fi
        ;;
    "view")
        view_secret "$2"
        ;;
    "redeploy")
        redeploy_services
        ;;
    "help"|"--help"|"-h"|"")
        usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        echo ""
        usage
        exit 1
        ;;
esac