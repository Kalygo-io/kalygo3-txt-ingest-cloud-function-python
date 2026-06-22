"""
Helper functions for Google Cloud Storage operations.
"""
import json
import base64
import logging
from google.cloud import storage
from singletons.environment_variables import EnvironmentVariables

logger = logging.getLogger(__name__)


class AccountGcsCredentialMissing(Exception):
    """Raised when an account has no usable GOOGLE_CLOUD_STORAGE credential."""
    pass


def get_storage_instance_for_account(account_id: int) -> storage.Client:
    """
    Build a Storage client from the account's own GCS service-account credential.

    Reads the GOOGLE_CLOUD_STORAGE credential row for the account and decrypts it
    in-memory (the service-account JSON is never logged). Raises
    AccountGcsCredentialMissing if the account has not configured GCS creds.
    """
    from db.database import init_database, get_db
    from db.credential_model import Credential
    from db.enums import CredentialType
    from helpers.credential_crypto import decrypt_credential_data

    if not account_id:
        raise AccountGcsCredentialMissing("Missing account_id; cannot resolve GCS credentials")

    init_database()
    db_gen = get_db()
    db = next(db_gen)
    try:
        credential = (
            db.query(Credential)
            .filter(
                Credential.account_id == account_id,
                Credential.credential_type == CredentialType.GOOGLE_CLOUD_STORAGE,
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
        raise AccountGcsCredentialMissing(
            f"Account {account_id} has no GOOGLE_CLOUD_STORAGE credential configured"
        )

    data = decrypt_credential_data(credential.encrypted_data)
    service_account_json = data.get("service_account_json")
    if not service_account_json:
        raise AccountGcsCredentialMissing(
            f"Account {account_id} GCS credential is missing service_account_json"
        )

    logger.info("Using per-account GCS credentials for account %s", account_id)
    return storage.Client.from_service_account_info(service_account_json)


def get_storage_instance() -> storage.Client:
    """
    Get Storage client instance with proper credentials.
    
    Returns:
        storage.Client: Initialized Storage client
    """
    try:
        # Check if KB_INGEST_SA is a base64-encoded JSON string
        if EnvironmentVariables.KB_INGEST_SA:
            try:
                # Try to decode as base64 first (common in Cloud Functions)
                key_json = base64.b64decode(EnvironmentVariables.KB_INGEST_SA).decode('utf-8')
                credentials = json.loads(key_json)
                return storage.Client(credentials=credentials)
            except (ValueError, json.JSONDecodeError):
                # If not base64, try as direct JSON string
                try:
                    credentials = json.loads(EnvironmentVariables.KB_INGEST_SA)
                    return storage.Client(credentials=credentials)
                except json.JSONDecodeError:
                    # If not JSON, might be a file path (for local testing)
                    import os
                    if os.path.exists(EnvironmentVariables.KB_INGEST_SA):
                        return storage.Client.from_service_account_json(EnvironmentVariables.KB_INGEST_SA)
                    else:
                        print(f"Warning: Service account key file not found: {EnvironmentVariables.KB_INGEST_SA}")
        
        # Fallback to default authentication (Application Default Credentials)
        return storage.Client()
    except Exception as error:
        print(f"Warning: Error loading service account credentials, falling back to default auth: {error}")
        return storage.Client()


def download_file_from_gcs(bucket_name: str, file_path: str, storage_client=None) -> str:
    """
    Download a file from Google Cloud Storage.

    Args:
        bucket_name: Name of the GCS bucket
        file_path: Path to the file within the bucket
        storage_client: Optional pre-built client (e.g. per-account credentials).

    Returns:
        File content as a string (UTF-8 decoded)
    """
    try:
        storage_client = storage_client or get_storage_instance()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        print(f"Downloading file from GCS: gs://{bucket_name}/{file_path}")
        
        # Download the file content
        content = blob.download_as_bytes()
        
        # Convert bytes to string (assuming UTF-8 encoding)
        file_content = content.decode('utf-8')
        
        print(f"Successfully downloaded file: {file_path}, size: {len(content)} bytes")
        
        return file_content
    except Exception as error:
        print(f"Error downloading file from GCS: gs://{bucket_name}/{file_path}, error: {error}")
        raise Exception(f"Failed to download file from GCS: {str(error)}")


def file_exists_in_gcs(bucket_name: str, file_path: str, storage_client=None) -> bool:
    """
    Check if a file exists in Google Cloud Storage.

    Args:
        bucket_name: Name of the GCS bucket
        file_path: Path to the file within the bucket
        storage_client: Optional pre-built client (e.g. per-account credentials).

    Returns:
        True if file exists, False otherwise
    """
    try:
        storage_client = storage_client or get_storage_instance()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        return blob.exists()
    except Exception as error:
        print(f"Error checking if file exists in GCS: gs://{bucket_name}/{file_path}, error: {error}")
        return False

