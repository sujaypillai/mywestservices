# Azure Services Explorer - Malaysia West

A Python Flask application that displays Azure services available in the Malaysia West region and provides an AI-powered chat interface to answer questions about service availability.

## Features

- 📋 Lists all Azure services available in Malaysia West region
- 🔍 Search functionality to filter services
- 💬 AI-powered chat to answer questions about service availability
- 📊 Statistics dashboard showing total services and providers
- 🎨 Modern, responsive UI with Bootstrap 5

## Local Development

### Prerequisites

- Python 3.9+
- Azure CLI (for deployment)
- Azure subscription (for live service data)

### Run Locally

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Open http://localhost:8000 in your browser.

## Deploy to Azure App Service

### Quick Deploy (One Command)

```bash
az webapp up \
  --name <your-unique-app-name> \
  --resource-group rg-malaysia-west-services \
  --location malaysiawest \
  --runtime "PYTHON:3.12" \
  --sku B1
```

### Configure Startup Command

```bash
az webapp config set \
  --name <your-app-name> \
  --resource-group rg-malaysia-west-services \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"
```

## Setup User-Assigned Managed Identity for Azure OpenAI

This app uses a **User-Assigned Managed Identity** to authenticate with Azure OpenAI (required when API key auth is disabled).

### Step 1: Create User-Assigned Managed Identity

```bash
# Set variables
RESOURCE_GROUP="rg-malaysia-west-services"
LOCATION="malaysiawest"
IDENTITY_NAME="id-azure-services-explorer"

# Create the managed identity
az identity create \
  --name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Get the Client ID (save this for later)
CLIENT_ID=$(az identity show \
  --name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --query clientId -o tsv)

echo "Managed Identity Client ID: $CLIENT_ID"

# Get the Principal ID (needed for role assignment)
PRINCIPAL_ID=$(az identity show \
  --name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --query principalId -o tsv)

echo "Managed Identity Principal ID: $PRINCIPAL_ID"
```

### Step 2: Grant Azure OpenAI Permissions

Assign the **"Cognitive Services OpenAI User"** role to the managed identity:

```bash
# Set your Azure OpenAI resource details
OPENAI_RESOURCE_GROUP="<your-openai-resource-group>"
OPENAI_ACCOUNT_NAME="<your-openai-account-name>"

# Get the Azure OpenAI resource ID
OPENAI_RESOURCE_ID=$(az cognitiveservices account show \
  --name $OPENAI_ACCOUNT_NAME \
  --resource-group $OPENAI_RESOURCE_GROUP \
  --query id -o tsv)

# Assign "Cognitive Services OpenAI User" role
# This grants the data action: Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action
az role assignment create \
  --assignee-object-id $PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope $OPENAI_RESOURCE_ID

echo "Role assignment complete!"
```

### Step 3: Assign Managed Identity to App Service

```bash
APP_NAME="<your-app-name>"

# Get the managed identity resource ID
IDENTITY_ID=$(az identity show \
  --name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --query id -o tsv)

# Assign the user-assigned managed identity to the web app
az webapp identity assign \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --identities $IDENTITY_ID
```

### Step 4: Configure App Settings

```bash
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    AZURE_OPENAI_ENDPOINT="https://<your-openai>.openai.azure.com/" \
    AZURE_OPENAI_DEPLOYMENT="gpt-5.2-chat" \
    AZURE_MANAGED_IDENTITY_CLIENT_ID="$CLIENT_ID"
```

### Step 5: Grant Reader Role for Azure Resources (Optional)

To fetch live Azure service data:

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az role assignment create \
  --assignee-object-id $PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Reader" \
  --scope /subscriptions/$SUBSCRIPTION_ID
```

## API Endpoints

| Endpoint                | Method | Description                                 |
| ----------------------- | ------ | ------------------------------------------- |
| `/`                     | GET    | Main page with services list                |
| `/api/services`         | GET    | JSON list of all services                   |
| `/api/search?q=<query>` | GET    | Search services by keyword                  |
| `/api/chat`             | POST   | Chat endpoint (body: `{"question": "..."}`) |
| `/api/export/csv`       | GET    | Download services as CSV                    |

## Project Structure

```
azure-malaysia-services/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── startup.sh          # Gunicorn startup script
├── .gitignore
└── templates/
    └── index.html      # Frontend template
```

## Environment Variables

| Variable                  | Required | Description                                         |
| ------------------------- | -------- | --------------------------------------------------- |
| `AZURE_SUBSCRIPTION_ID`   | No       | Azure subscription (auto-detected if authenticated) |
| `AZURE_OPENAI_ENDPOINT`   | No       | Azure OpenAI endpoint for chat                      |
| `AZURE_OPENAI_API_KEY`    | No       | Azure OpenAI API key                                |
| `AZURE_OPENAI_DEPLOYMENT` | No       | Model deployment name (default: gpt-4o)             |

## License

MIT
