"""
Helper functions for accessing Google Secret Manager.
"""
from google.cloud import secretmanager
from typing import Optional

# Cache for secrets to avoid repeated API calls
_secrets_cache: dict[str, str] = {}

def get_secret(secret_name: str, project_id: str = "830723611668") -> str:
    """
    Retrieve a secret from Google Secret Manager.
    
    Args:
        secret_name: Name of the secret to retrieve
        project_id: GCP project ID (default: 830723611668)
    
    Returns:
        The secret value as a string
    """
    # Check cache first
    if secret_name in _secrets_cache:
        return _secrets_cache[secret_name]
    
    try:
        # Initialize the Secret Manager client
        client = secretmanager.SecretManagerServiceClient()
        
        # Build the resource name of the secret version
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        
        # Access the secret version
        response = client.access_secret_version(request={"name": name})
        
        # Decode the secret value
        secret = response.payload.data.decode("UTF-8")
        
        # Cache the secret
        _secrets_cache[secret_name] = secret
        
        return secret
    except Exception as error:
        print(f"Error retrieving secret '{secret_name}': {error}")
        raise

