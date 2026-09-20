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


def pinecone_api_key_for_account(account_id: int) -> str:
    """
    Resolve an account's own Pinecone API key from the credentials table.

    Reads the PINECONE_API_KEY credential row for the account and decrypts it
    in-memory (the key is never logged). This makes ingestion use the SAME
    per-account Pinecone project the API microservice reads/manages with, so the
    chosen index actually receives the data. Raises ValueError if the account has
    no Pinecone credential configured.
    """
    # Imported lazily so the module loads even if DB deps are unavailable
    # (mirrors get_storage_instance_for_account in helpers/gcs.py).
    from db.database import init_database, get_db
    from db.credential_model import Credential
    from db.enums import CredentialType
    from helpers.credential_crypto import decrypt_credential_data

    if not account_id:
        raise ValueError("Missing account_id; cannot resolve Pinecone credentials")

    init_database()
    db_gen = get_db()
    db = next(db_gen)
    try:
        credential = (
            db.query(Credential)
            .filter(
                Credential.account_id == account_id,
                Credential.credential_type == CredentialType.PINECONE_API_KEY,
            )
            .order_by(Credential.updated_at.desc())
            .first()
        )
    finally:
        try:
            db.close()
        except Exception:
            pass

    if not credential:
        raise ValueError(f"Account {account_id} has no PINECONE_API_KEY credential configured")

    data = decrypt_credential_data(credential.encrypted_data)
    api_key = data.get("api_key")
    if not api_key:
        raise ValueError(f"Account {account_id} Pinecone credential is missing api_key")

    print(f"Using per-account Pinecone credentials for account {account_id}")
    return api_key


def initialize_pinecone(api_key: str = None) -> Pinecone:
    """
    Initialize Pinecone client.

    Args:
        api_key: Account's Pinecone API key. When omitted, falls back to the
            globally configured PINECONE_API_KEY (legacy/default).

    Returns:
        Pinecone: Initialized Pinecone client
    """
    api_key = api_key or EnvironmentVariables.PINECONE_API_KEY

    if not api_key:
        raise ValueError('A Pinecone API key is required')

    # Never log the key (or any prefix of it).
    print('Initializing Pinecone client')

    try:
        pinecone = Pinecone(api_key=api_key)
        print('Pinecone client initialized successfully')
        return pinecone
    except Exception as error:
        print(f"Error initializing Pinecone client: {error}")
        raise


def get_pinecone_index(index_name: str = None, api_key: str = None):
    """
    Get Pinecone index instance.

    Args:
        index_name: Target Pinecone index. When omitted, falls back to the
            globally configured PINECONE_ALL_MINILM_L6_V2_INDEX (legacy/default).
        api_key: Account's Pinecone API key (see initialize_pinecone).

    Returns:
        Index: Pinecone index instance
    """
    pinecone = initialize_pinecone(api_key)
    index_name = index_name or EnvironmentVariables.PINECONE_ALL_MINILM_L6_V2_INDEX

    if not index_name:
        raise ValueError('A Pinecone index name is required')
    
    print(f'Getting Pinecone index: {index_name}')
    
    try:
        index = pinecone.Index(index_name)
        print('Pinecone index retrieved successfully')
        return index
    except Exception as error:
        print(f"Error getting Pinecone index: {error}")
        raise


def test_pinecone_connection(api_key: str = None) -> bool:
    """
    Test Pinecone connection.

    Args:
        api_key: Account's Pinecone API key (see initialize_pinecone).

    Returns:
        bool: True if connection is successful
    """
    try:
        print('Testing Pinecone connection...')
        pinecone = initialize_pinecone(api_key)
        
        # Try to list indexes to test connection
        indexes = pinecone.list_indexes()
        print(f'Available indexes: {indexes}')
        
        return True
    except Exception as error:
        print(f"Pinecone connection test failed: {error}")
        return False


def upsert_vectors(
    vectors: List[VectorData],
    namespace: str = 'similarity_search',
    index_name: str = None,
    api_key: str = None
) -> None:
    """
    Upsert vectors to Pinecone in batches.

    Args:
        vectors: List of VectorData objects to upsert
        namespace: Namespace to upsert vectors to (default: 'similarity_search')
        index_name: Target Pinecone index. When omitted, falls back to the
            globally configured index (legacy/default).
        api_key: Account's Pinecone API key. When omitted, falls back to the
            globally configured PINECONE_API_KEY (legacy/default).
    """
    print(f"Starting upsert of {len(vectors)} vectors to namespace: {namespace}")

    # Test connection first
    connection_ok = test_pinecone_connection(api_key)
    if not connection_ok:
        raise Exception('Pinecone connection test failed')

    index = get_pinecone_index(index_name, api_key)
    
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

