"""
Azure Services Explorer for Malaysia West Region
A Flask app that displays and answers questions about Azure services in Malaysia West.
"""

import os
import json
from flask import Flask, render_template, request, jsonify
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
import requests
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)

# Cache for services data
_services_cache = None


def get_azure_credential():
    """
    Get the appropriate Azure credential based on environment.
    - In Azure App Service with User-Assigned Managed Identity: use ManagedIdentityCredential with client_id
    - Locally: use DefaultAzureCredential (az login)
    """
    managed_identity_client_id = os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID")
    
    if managed_identity_client_id:
        # Use User-Assigned Managed Identity in Azure
        return ManagedIdentityCredential(client_id=managed_identity_client_id)
    else:
        # Use DefaultAzureCredential for local development (az login)
        return DefaultAzureCredential()


def get_deployable_resources_in_region(region: str = "Malaysia West"):
    """
    Fetch all deployable resource types available in a specific Azure region.
    
    Equivalent to the PowerShell script:
        $providers = Get-AzResourceProvider
        foreach ($provider in $providers) {
            foreach ($resourceType in $provider.ResourceTypes) {
                if ($resourceType.Locations -contains $region) { ... }
            }
        }
    
    Args:
        region: The Azure region name (e.g., "Malaysia West")
    
    Returns:
        List of resource types available in the specified region
    """
    try:
        credential = get_azure_credential()
        
        # Use subscription ID from environment, or try to get from Azure
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        
        if not subscription_id:
            # Try to get subscription ID from Azure
            subscription_client = SubscriptionClient(credential)
            for sub in subscription_client.subscriptions.list():
                subscription_id = sub.subscription_id
                break
        
        if not subscription_id:
            raise Exception("No Azure subscription found. Please set AZURE_SUBSCRIPTION_ID environment variable.")
        
        # Use ResourceManagementClient to get providers (equivalent to Get-AzResourceProvider)
        resource_client = ResourceManagementClient(credential, subscription_id)
        
        # Initialize array to hold results (equivalent to $results = @())
        results = []
        
        # Get all resource providers (equivalent to Get-AzResourceProvider)
        providers = resource_client.providers.list()
        
        for provider in providers:
            namespace = provider.namespace  # equivalent to $provider.ProviderNamespace
            
            for resource_type in provider.resource_types or []:
                locations = resource_type.locations or []  # equivalent to $resourceType.Locations
                
                # Check if region is in locations (equivalent to if ($locations -contains $region))
                if region in locations:
                    results.append({
                        "provider": namespace,
                        "resource_type": resource_type.resource_type,
                        "display_name": f"{namespace}/{resource_type.resource_type}",
                        "is_available": "Yes",
                        "api_versions": resource_type.api_versions[:3] if resource_type.api_versions else []
                    })
        
        return results
        
    except Exception as e:
        print(f"Error fetching resource providers: {e}")
        raise


def get_malaysia_west_services():
    """Fetch Azure services available in Malaysia West region."""
    global _services_cache
    
    if _services_cache is not None:
        return _services_cache
    
    try:
        # Use the converted PowerShell function to get deployable resources
        services = get_deployable_resources_in_region("Malaysia West")
        
        if services:
            _services_cache = services
            print(f"Successfully loaded {len(services)} resource types from Azure")
            return services
        else:
            print("No services found, this might indicate an issue with the region name")
            return []
        
    except Exception as e:
        print(f"Error fetching services: {e}")
        print("Note: Make sure you are logged in with 'az login' and have access to a subscription")
        return []


def get_ai_response(question: str, services: list) -> str:
    """Generate AI response about Azure services in Malaysia West using Azure OpenAI."""
    
    # Get Azure OpenAI configuration from environment
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2-chat")
    managed_identity_client_id = os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID")
    api_version = "2024-12-01-preview"
    
    if not endpoint:
        # Fallback to rule-based response if no AI configured
        return generate_simple_response(question, services)
    
    try:
        from azure.identity import get_bearer_token_provider
        
        # Use User-Assigned Managed Identity if client_id is provided
        # Otherwise fall back to DefaultAzureCredential (for local dev)
        if managed_identity_client_id:
            credential = ManagedIdentityCredential(client_id=managed_identity_client_id)
        else:
            credential = DefaultAzureCredential()
        
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default"
        )
        
        # Initialize Azure OpenAI client with Azure AD auth
        client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
        )
        
        # Group services by provider for better context
        providers = {}
        for s in services:
            provider = s['provider']
            if provider not in providers:
                providers[provider] = []
            providers[provider].append(s['resource_type'])
        
        # Create a comprehensive but concise service summary
        provider_summary = []
        for provider, resource_types in sorted(providers.items()):
            types_str = ", ".join(resource_types[:5])
            if len(resource_types) > 5:
                types_str += f" (+{len(resource_types) - 5} more)"
            provider_summary.append(f"- {provider}: {types_str}")
        
        service_context = "\n".join(provider_summary)
        
        system_prompt = f"""You are an Azure expert assistant helping users understand Azure services available in the Malaysia West region.

IMPORTANT RULES:
1. ONLY mention services that are explicitly listed below as available in Malaysia West
2. DO NOT suggest or recommend services that are not in this list
3. If a user asks about a service not in the list, clearly state it is NOT available in Malaysia West
4. DO NOT make up or hallucinate alternative services - only reference what's in the list below
5. Be honest if you're unsure - say "based on the available data" rather than guessing

Azure providers and resource types available in Malaysia West ({len(services)} total resources from {len(providers)} providers):

{service_context}

When answering:
- Be concise and accurate
- Only suggest alternatives if they are explicitly in the list above
- If asked about unavailable services, simply state they're not available - don't invent alternatives"""

        # Call Azure OpenAI using the SDK
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            max_completion_tokens=500,
            model=deployment
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"AI API error: {e}")
        return generate_simple_response(question, services)


def search_services(query: str, services: list) -> list:
    """
    Search services dynamically based on query keywords.
    Returns matching services from the services list.
    """
    query_lower = query.lower()
    
    # Service-specific mappings for more precise searches
    # Maps common search terms to their actual Azure provider namespaces
    service_mappings = {
        'sql': ['microsoft.sql'],
        'azure sql': ['microsoft.sql'],
        'sql server': ['microsoft.sql'],
        'sql database': ['microsoft.sql'],
        'postgres': ['microsoft.dbforpostgresql'],
        'postgresql': ['microsoft.dbforpostgresql'],
        'mysql': ['microsoft.dbformysql'],
        'maria': ['microsoft.dbformariadb'],
        'mariadb': ['microsoft.dbformariadb'],
        'cosmos': ['microsoft.documentdb'],
        'cosmosdb': ['microsoft.documentdb'],
        'redis': ['microsoft.cache'],
        'kubernetes': ['microsoft.kubernetes', 'microsoft.containerservice'],
        'aks': ['microsoft.containerservice'],
        'container': ['microsoft.containerinstance', 'microsoft.containerregistry', 'microsoft.containerservice'],
        'vm': ['microsoft.compute'],
        'virtual machine': ['microsoft.compute'],
        'storage': ['microsoft.storage'],
        'blob': ['microsoft.storage'],
        'function': ['microsoft.web'],
        'functions': ['microsoft.web'],
        'app service': ['microsoft.web'],
        'logic app': ['microsoft.logic'],
        'key vault': ['microsoft.keyvault'],
        'keyvault': ['microsoft.keyvault'],
        'cognitive': ['microsoft.cognitiveservices'],
        'ai': ['microsoft.cognitiveservices', 'microsoft.machinelearningservices'],
        'machine learning': ['microsoft.machinelearningservices'],
        'event hub': ['microsoft.eventhub'],
        'eventhub': ['microsoft.eventhub'],
        'service bus': ['microsoft.servicebus'],
        'servicebus': ['microsoft.servicebus'],
    }
    
    # Check if query matches any specific service mapping
    for term, providers in service_mappings.items():
        if term in query_lower:
            matches = []
            for service in services:
                provider_lower = service["provider"].lower()
                if provider_lower in providers:
                    matches.append(service)
            if matches:
                return matches
    
    # Extract keywords from the query (remove common words)
    stop_words = {'is', 'are', 'the', 'a', 'an', 'in', 'available', 'does', 'do', 'can', 'i', 'use', 
                  'deploy', 'what', 'which', 'how', 'about', 'tell', 'me', 'show', 'get', 'have',
                  'malaysia', 'west', 'region', 'azure', 'service', 'services'}
    
    words = query_lower.replace('?', '').replace(',', '').split()
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Search through services
    matches = []
    for service in services:
        display_name_lower = service["display_name"].lower()
        provider_lower = service["provider"].lower()
        resource_type_lower = service["resource_type"].lower()
        
        # Check if any keyword matches
        for keyword in keywords:
            if (keyword in display_name_lower or 
                keyword in provider_lower or 
                keyword in resource_type_lower):
                matches.append(service)
                break
    
    return matches


def is_casual_conversation(question: str) -> tuple[bool, str]:
    """
    Check if the question is casual conversation (greeting, etc.) rather than a service query.
    Returns (is_casual, response) tuple.
    """
    question_lower = question.lower().strip()
    
    # Common greetings and casual phrases
    greetings = ['hi', 'hello', 'hey', 'hi there', 'hello there', 'hey there', 
                 'good morning', 'good afternoon', 'good evening', 'howdy',
                 'greetings', 'hiya', 'yo', 'sup', "what's up", 'whats up']
    
    # Check for exact matches or close matches
    for greeting in greetings:
        if question_lower == greeting or question_lower == greeting + '!' or question_lower == greeting + '.':
            return True, "👋 Hello! I'm here to help you explore Azure services available in the Malaysia West region. You can ask me questions like:\n\n• What services are available?\n• Is Azure SQL available?\n• Tell me about container services\n• How many services are there?\n\nWhat would you like to know?"
    
    # Handle "how are you" type questions
    how_are_you = ['how are you', "how's it going", 'how are you doing', "what's going on"]
    for phrase in how_are_you:
        if phrase in question_lower:
            return True, "😊 I'm doing great, thanks for asking! I'm ready to help you explore Azure services in the Malaysia West region. What would you like to know about?"
    
    # Handle thanks/gratitude
    thanks = ['thank you', 'thanks', 'thx', 'ty', 'appreciate it', 'cheers']
    for phrase in thanks:
        if phrase in question_lower:
            return True, "You're welcome! 😊 Feel free to ask if you have more questions about Azure services in Malaysia West."
    
    # Handle help requests
    help_phrases = ['help', 'what can you do', 'what do you do', 'how does this work']
    for phrase in help_phrases:
        if phrase in question_lower:
            return True, "🤖 I'm an Azure Services Explorer for the Malaysia West region. I can help you:\n\n• Find out which Azure services are available in Malaysia West\n• Search for specific services (e.g., 'storage', 'compute', 'AI')\n• Get service counts and summaries\n• Answer questions about Azure capabilities in this region\n\nJust type your question and I'll do my best to help!"
    
    return False, ""


def generate_simple_response(question: str, services: list) -> str:
    """Generate a dynamic response by searching the services list."""
    question_lower = question.lower()
    
    # Check for casual conversation first
    is_casual, casual_response = is_casual_conversation(question)
    if is_casual:
        return casual_response
    
    # Handle general queries
    if "how many" in question_lower:
        providers = set(s["provider"] for s in services)
        return f"There are {len(services)} Azure resource types available in Malaysia West from {len(providers)} different providers."
    
    if "list all" in question_lower or "show all" in question_lower:
        providers = {}
        for service in services:
            provider = service["provider"]
            if provider not in providers:
                providers[provider] = 0
            providers[provider] += 1
        provider_summary = [f"• {p}: {count} resource types" for p, count in list(providers.items())[:15]]
        return f"There are {len(services)} resource types from {len(providers)} providers available in Malaysia West:\n\n" + "\n".join(provider_summary) + "\n\n...and more."
    
    # Search for specific services based on the query
    matches = search_services(question, services)
    
    if matches:
        # Group matches by provider
        providers = {}
        for match in matches:
            provider = match["provider"]
            if provider not in providers:
                providers[provider] = []
            providers[provider].append(match["resource_type"])
        
        # Build response
        if len(matches) == 1:
            m = matches[0]
            return f"✅ Yes! **{m['display_name']}** is available in Malaysia West."
        elif len(matches) <= 10:
            response = f"✅ Found {len(matches)} matching services in Malaysia West:\n\n"
            for provider, resource_types in providers.items():
                response += f"**{provider}**:\n"
                for rt in resource_types:
                    response += f"  • {rt}\n"
            return response
        else:
            response = f"✅ Found {len(matches)} matching resource types in Malaysia West:\n\n"
            for provider, resource_types in list(providers.items())[:5]:
                response += f"**{provider}**: {', '.join(resource_types[:5])}"
                if len(resource_types) > 5:
                    response += f" (+{len(resource_types) - 5} more)"
                response += "\n"
            if len(providers) > 5:
                response += f"\n...and {len(providers) - 5} more providers."
            return response
    else:
        return f"❌ No services matching your query were found in Malaysia West. Try searching for specific terms like 'container', 'sql', 'storage', 'compute', etc."


@app.route("/")
def index():
    """Render the main page with services list."""
    services = get_malaysia_west_services()
    
    # Group by provider for better display
    grouped = {}
    for service in services:
        provider = service["provider"]
        if provider not in grouped:
            grouped[provider] = []
        grouped[provider].append(service)
    
    return render_template("index.html", 
                         services=services, 
                         grouped_services=grouped,
                         total_count=len(services),
                         provider_count=len(grouped))


@app.route("/api/services")
def api_services():
    """API endpoint to get all services."""
    services = get_malaysia_west_services()
    return jsonify({
        "region": "Malaysia West",
        "total_services": len(services),
        "services": services
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """API endpoint for chat functionality."""
    data = request.get_json()
    question = data.get("question", "")
    
    if not question:
        return jsonify({"error": "Question is required"}), 400
    
    services = get_malaysia_west_services()
    response = get_ai_response(question, services)
    
    return jsonify({
        "question": question,
        "answer": response
    })


@app.route("/api/search")
def search():
    """Search services by keyword."""
    query = request.args.get("q", "").lower()
    services = get_malaysia_west_services()
    
    if not query:
        return jsonify({"results": services})
    
    filtered = [s for s in services if query in s["display_name"].lower()]
    return jsonify({
        "query": query,
        "count": len(filtered),
        "results": filtered
    })


@app.route("/api/export/csv")
def export_csv():
    """
    Export services to CSV format.
    Equivalent to PowerShell: $results | Export-Csv -Path $outputCsv -NoTypeInformation
    """
    import csv
    from io import StringIO
    from flask import Response
    
    services = get_malaysia_west_services()
    
    # Create CSV in memory
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["ProviderNamespace", "ResourceType", "IsAvailableInMYW"])
    writer.writeheader()
    
    for service in services:
        writer.writerow({
            "ProviderNamespace": service["provider"],
            "ResourceType": service["resource_type"],
            "IsAvailableInMYW": service.get("is_available", "Yes")
        })
    
    # Return as downloadable CSV file
    response = Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=DeployableResourcesIn_MalaysiaWest.csv"}
    )
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
