#!/bin/bash
set -e

# =============================================================================
# Azure Malaysia Services Explorer - Deployment Script
# =============================================================================

# Configuration - UPDATE THESE VALUES
APP_NAME="azure-my-services"  # Must be globally unique
RESOURCE_GROUP="rg-malaysia-west-services"
LOCATION="malaysiawest"
IDENTITY_NAME="id-azure-services-explorer"

# Azure OpenAI Configuration (from your .env)
AZURE_OPENAI_ENDPOINT="https://skyway-dev-openai.openai.azure.com/"
AZURE_OPENAI_DEPLOYMENT="gpt-5.2-chat"
AZURE_SUBSCRIPTION_ID="85f1fd10-cc71-485c-ae43-bde6131f16bd"

# Managed Identity Client ID (will be retrieved after creation)
MANAGED_IDENTITY_CLIENT_ID="dd17bb61-5e67-4294-aa6b-0d5e9675bc9e"

echo "=============================================="
echo "Deploying Azure Services Explorer"
echo "=============================================="
echo "App Name: $APP_NAME"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "=============================================="

# Step 1: Check Azure CLI login
echo ""
echo "Step 1: Checking Azure CLI authentication..."
az account show --query "{Name:name, SubscriptionId:id}" -o table || {
    echo "ERROR: Not logged in. Please run 'az login' first."
    exit 1
}

# Step 2: Create Resource Group (if not exists)
echo ""
echo "Step 2: Creating resource group..."
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none 2>/dev/null || true
echo "✅ Resource group ready: $RESOURCE_GROUP"

# Step 3: Check if Web App exists, deploy or update accordingly
echo ""
echo "Step 3: Checking web app status..."
APP_EXISTS=$(az webapp show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "name" -o tsv 2>/dev/null || echo "")

if [ -z "$APP_EXISTS" ]; then
    echo "Web app not found. Creating new web app..."
    az webapp up \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --runtime "PYTHON:3.12" \
        --sku B1
    echo "✅ Web app created: $APP_NAME"
else
    echo "Web app already exists. Deploying code update..."
    az webapp up \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP"
    echo "✅ Web app updated: $APP_NAME"
fi

# Step 4: Configure startup command
echo ""
echo "Step 4: Configuring startup command..."
az webapp config set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app" \
    --output none

echo "✅ Startup command configured"

# Step 5: Check if managed identity exists, create if not
echo ""
echo "Step 5: Setting up managed identity..."
IDENTITY_EXISTS=$(az identity show \
    --name "$IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "clientId" -o tsv 2>/dev/null || echo "")

if [ -z "$IDENTITY_EXISTS" ]; then
    echo "Creating new managed identity..."
    az identity create \
        --name "$IDENTITY_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
fi

# Get the managed identity details
MANAGED_IDENTITY_CLIENT_ID=$(az identity show \
    --name "$IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "clientId" -o tsv)

IDENTITY_RESOURCE_ID=$(az identity show \
    --name "$IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "id" -o tsv)

echo "✅ Managed Identity Client ID: $MANAGED_IDENTITY_CLIENT_ID"

# Step 6: Assign managed identity to web app
echo ""
echo "Step 6: Assigning managed identity to web app..."
az webapp identity assign \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --identities "$IDENTITY_RESOURCE_ID" \
    --output none

echo "✅ Managed identity assigned to web app"

# Step 7: Configure App Settings (Environment Variables)
echo ""
echo "Step 7: Configuring app settings..."
az webapp config appsettings set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
        AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
        AZURE_OPENAI_DEPLOYMENT="$AZURE_OPENAI_DEPLOYMENT" \
        AZURE_MANAGED_IDENTITY_CLIENT_ID="$MANAGED_IDENTITY_CLIENT_ID" \
        AZURE_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID" \
        SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
    --output none

echo "✅ App settings configured"

# Step 8: Grant Reader role to managed identity for Azure resources
echo ""
echo "Step 8: Granting Reader role for Azure resource discovery..."
PRINCIPAL_ID=$(az identity show \
    --name "$IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "principalId" -o tsv)

az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Reader" \
    --scope "/subscriptions/$AZURE_SUBSCRIPTION_ID" \
    --output none 2>/dev/null || echo "Reader role may already exist"

echo "✅ Reader role assigned"

# Step 9: Reminder about Azure OpenAI permissions
echo ""
echo "=============================================="
echo "⚠️  IMPORTANT: Azure OpenAI Permissions"
echo "=============================================="
echo "Make sure the managed identity has 'Cognitive Services OpenAI User' role"
echo "on your Azure OpenAI resource. Run this command:"
echo ""
echo "az role assignment create \\"
echo "    --assignee-object-id $PRINCIPAL_ID \\"
echo "    --assignee-principal-type ServicePrincipal \\"
echo "    --role \"Cognitive Services OpenAI User\" \\"
echo "    --scope \"/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<openai-name>\""
echo ""

# Step 10: Restart the app
echo "Step 10: Restarting web app..."
az webapp restart \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP"

echo "✅ Web app restarted"

# Done!
echo ""
echo "=============================================="
echo "🎉 Deployment Complete!"
echo "=============================================="
echo ""
echo "App URL: https://$APP_NAME.azurewebsites.net"
echo ""
echo "To view logs:"
echo "  az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "To view app settings:"
echo "  az webapp config appsettings list --name $APP_NAME --resource-group $RESOURCE_GROUP -o table"
echo ""
