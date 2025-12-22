"""
Helper functions for fetching embeddings from the embedding API service.
"""
import os
import requests
from typing import List
from singletons.environment_variables import EnvironmentVariables


def fetch_embedding(jwt: str, text: str) -> List[float]:
    """
    Fetch embedding from the embedding API service.
    
    Args:
        jwt: JWT token for authentication
        text: Text to embed
    
    Returns:
        List[float]: The embedding vector
    """
    try:
        api_url = EnvironmentVariables.EMBEDDINGS_API_URL or \
                  os.getenv('EMBEDDINGS_API_URL') or \
                  'https://kalygo-embeddings-service-830723611668.us-east1.run.app/huggingface/embedding'
        
        response = requests.post(
            api_url,
            json={"input": text},
            headers={
                'Content-Type': 'application/json',
                'Cookie': f'jwt={jwt}'
            },
            timeout=120  # 120 second timeout
        )
        
        response.raise_for_status()
        
        response_data = response.json()
        
        print(f"Embedding API response structure: {list(response_data.keys()) if isinstance(response_data, dict) else 'array'}")
        print(f"Response data type: {type(response_data)}")
        
        # Handle different possible response formats
        embedding_array = None
        
        if isinstance(response_data, dict) and 'embedding' in response_data:
            embedding_array = response_data['embedding']
        elif isinstance(response_data, list):
            embedding_array = response_data
        elif isinstance(response_data, dict) and 'data' in response_data and isinstance(response_data['data'], list):
            embedding_array = response_data['data']
        else:
            print(f"Unexpected response format: {response_data}")
            raise ValueError('Invalid response format from embedding API')
        
        # Ensure all values are numbers and flatten if necessary
        def flatten_array(arr):
            """Recursively flatten nested arrays and convert to float."""
            result = []
            for item in arr:
                if isinstance(item, (list, tuple)):
                    result.extend(flatten_array(item))
                else:
                    num = float(item)
                    if num != num:  # Check for NaN
                        raise ValueError(f"Invalid embedding value: {item}")
                    result.append(num)
            return result
        
        flattened_embedding = flatten_array(embedding_array)
        
        print(f"Generated embedding with {len(flattened_embedding)} dimensions")
        print(f"First few values: {flattened_embedding[:5]}")
        
        return flattened_embedding
        
    except requests.exceptions.RequestException as error:
        print(f"Error fetching embedding (HTTP error): {error}")
        raise Exception(f"Failed to fetch embedding: {str(error)}")
    except Exception as error:
        print(f"Error fetching embedding: {error}")
        raise Exception(f"Failed to fetch embedding: {str(error)}")

