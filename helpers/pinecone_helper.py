"""
Helper functions for Pinecone vector database operations.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pinecone import Pinecone, ServerlessSpec
from singletons.environment_variables import EnvironmentVariables


@dataclass
class VectorData:
    """Data structure for a vector to be stored in Pinecone."""
    id: str
    values: List[float]
    metadata: Dict[str, Any]


@dataclass
class ProcessingResult:
    """Result of processing a file."""
    success: bool
    filename: str
    total_chunks_created: Optional[int] = None
    successful_uploads: Optional[int] = None
    failed_uploads: Optional[int] = None
    file_size_bytes: Optional[int] = None
    error: Optional[str] = None


def initialize_pinecone() -> Pinecone:
    """
    Initialize Pinecone client.
    
    Returns:
        Pinecone: Initialized Pinecone client
    """
    api_key = EnvironmentVariables.PINECONE_API_KEY
    
    if not api_key:
        raise ValueError('PINECONE_API_KEY environment variable is required')
    
    print('Initializing Pinecone client with:')
    print(f'- API Key: {api_key[:8]}...')
    
    try:
        pinecone = Pinecone(api_key=api_key)
        print('Pinecone client initialized successfully')
        return pinecone
    except Exception as error:
        print(f"Error initializing Pinecone client: {error}")
        raise


def get_pinecone_index():
    """
    Get Pinecone index instance.
    
    Returns:
        Index: Pinecone index instance
    """
    pinecone = initialize_pinecone()
    index_name = EnvironmentVariables.PINECONE_ALL_MINILM_L6_V2_INDEX
    
    if not index_name:
        raise ValueError('PINECONE_ALL_MINILM_L6_V2_INDEX environment variable is required')
    
    print(f'Getting Pinecone index: {index_name}')
    
    try:
        index = pinecone.Index(index_name)
        print('Pinecone index retrieved successfully')
        return index
    except Exception as error:
        print(f"Error getting Pinecone index: {error}")
        raise


def test_pinecone_connection() -> bool:
    """
    Test Pinecone connection.
    
    Returns:
        bool: True if connection is successful
    """
    try:
        print('Testing Pinecone connection...')
        pinecone = initialize_pinecone()
        
        # Try to list indexes to test connection
        indexes = pinecone.list_indexes()
        print(f'Available indexes: {indexes}')
        
        return True
    except Exception as error:
        print(f"Pinecone connection test failed: {error}")
        return False


def upsert_vectors(vectors: List[VectorData], namespace: str = 'similarity_search') -> None:
    """
    Upsert vectors to Pinecone in batches.
    
    Args:
        vectors: List of VectorData objects to upsert
        namespace: Namespace to upsert vectors to (default: 'similarity_search')
    """
    print(f"Starting upsert of {len(vectors)} vectors to namespace: {namespace}")
    
    # Test connection first
    connection_ok = test_pinecone_connection()
    if not connection_ok:
        raise Exception('Pinecone connection test failed')
    
    index = get_pinecone_index()
    
    try:
        print('📊 Vectors to be inserted:')
        print(f'   Count: {len(vectors)}')
        if vectors:
            print(f'   First vector ID: {vectors[0].id[:12]}...')
            print(f'   First vector dimensions: {len(vectors[0].values)}')
            print(f'   Sample values from first vector: {vectors[0].values[:3]}')
        print(f'   Namespace: {namespace}')
    except Exception as diagnostic_error:
        print(f'⚠️  Diagnostic check failed: {diagnostic_error}')
    
    # Pinecone recommends batch sizes of 100 or less
    batch_size = 100
    
    # Convert VectorData objects to dictionaries for Pinecone API
    vectors_dict = [
        {
            "id": v.id,
            "values": v.values,
            "metadata": v.metadata
        }
        for v in vectors
    ]
    
    for i in range(0, len(vectors_dict), batch_size):
        batch = vectors_dict[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(vectors_dict) + batch_size - 1) // batch_size
        
        try:
            print(f"Upserting batch {batch_num} with {len(batch)} vectors")
            index.upsert(vectors=batch, namespace=namespace)
            print(f"Successfully upserted batch {batch_num} of {total_batches}")
        except Exception as error:
            print(f"Error upserting batch {batch_num}: {error}")
            raise

