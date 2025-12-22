import base64
import json
import functions_framework
from flask import Request
from cloudevents.http import CloudEvent
from helpers.gcs import download_file_from_gcs, file_exists_in_gcs
from helpers.text_processor import process_text_file
from helpers.pinecone_helper import upsert_vectors, ProcessingResult
from helpers.get_secret import get_secret
from singletons.environment_variables import EnvironmentVariables


def _process_message(message: str, attributes: dict) -> ProcessingResult:
    """
    Internal function to process a Pub/Sub message.
    Extracted to be reusable by both CloudEvent and HTTP handlers.
    """
    # Parse the message
    parsed_message = json.loads(message)
    print(f"Decoded message: {json.dumps(parsed_message, indent=2)}")
    print(f"Message attributes: {attributes}")
    
    # Extract fields
    filename = parsed_message.get("filename")
    gcs_bucket = parsed_message.get("gcs_bucket")
    gcs_file_path = parsed_message.get("gcs_file_path")
    file_size = parsed_message.get("file_size", 0)
    content_type = parsed_message.get("content_type", "")
    user_id = parsed_message.get("user_id", "")
    user_email = parsed_message.get("user_email", "")
    namespace = parsed_message.get("namespace", "reranking")
    upload_timestamp = parsed_message.get("upload_timestamp", "")
    processing_status = parsed_message.get("processing_status", "")
    jwt = parsed_message.get("jwt")
    
    # Validate required fields
    if not filename or not gcs_bucket or not gcs_file_path:
        raise ValueError("Missing required fields: filename, gcs_bucket, or gcs_file_path")
    
    # Validate file type (TXT and MD files are supported)
    file_extension = filename.lower()
    if not file_extension.endswith('.txt') and not file_extension.endswith('.md'):
        raise ValueError("Only TXT & MD files are supported")
    
    # Check if JWT is provided
    if not jwt:
        raise ValueError("JWT token is required for embedding API calls")
    
    # Step 1: Download file from GCS
    print(f"Step 1: Downloading file from GCS: gs://{gcs_bucket}/{gcs_file_path}")
    
    # Check if file exists first
    file_exists = file_exists_in_gcs(gcs_bucket, gcs_file_path)
    if not file_exists:
        raise ValueError(f"File does not exist in GCS: gs://{gcs_bucket}/{gcs_file_path}")
    
    file_content = download_file_from_gcs(gcs_bucket, gcs_file_path)
    
    if not file_content.strip():
        raise ValueError("File is empty")
    
    # Step 2: Process file based on type and generate embeddings
    vectors = []
    successful_rows = 0
    failed_rows = 0
    
    # Process TXT or MD file
    print(f"Step 2: Processing text file: {filename}")
    text_result = process_text_file(
        file_content,
        filename,
        jwt
    )
    vectors = text_result["vectors"]
    successful_rows = text_result["successful_chunks"]
    failed_rows = text_result["failed_chunks"]
    print(f"Text processing complete: {successful_rows} successful, {failed_rows} failed")
    
    # Step 3: Insert embeddings into Pinecone
    print(f"Step 3: Inserting {len(vectors)} vectors into Pinecone")
    if vectors:
        upsert_vectors(vectors, namespace)
    
    # Prepare result
    result = ProcessingResult(
        success=True,
        filename=filename,
        total_chunks_created=successful_rows + failed_rows,
        successful_uploads=successful_rows,
        failed_uploads=failed_rows,
        file_size_bytes=file_size
    )
    
    print(f"Processing completed successfully: {result}")
    
    return result


@functions_framework.cloud_event
def process_txt_ingest_topic_message(cloud_event: CloudEvent) -> ProcessingResult:
    """
    Pub/Sub-triggered Cloud Function to process text/markdown files.
    
    Expected message format:
    {
        "file_id": string,
        "filename": string,
        "gcs_bucket": string,
        "gcs_file_path": string,
        "file_size": number,
        "content_type": string,
        "user_id": string,
        "user_email": string,
        "namespace": string (optional, defaults to "reranking"),
        "upload_timestamp": string,
        "processing_status": string,
        "jwt": string (required for embedding API)
    }
    """
    message = "{}"
    attributes = {}
    
    try:
        # Load secrets from Google Secret Manager
        EnvironmentVariables.EMBEDDINGS_API_URL = get_secret("EMBEDDINGS_API_URL")
        EnvironmentVariables.PINECONE_API_KEY = get_secret("PINECONE_API_KEY")
        EnvironmentVariables.PINECONE_ALL_MINILM_L6_V2_INDEX = get_secret("PINECONE_ALL_MINILM_L6_V2_INDEX")
        EnvironmentVariables.KB_INGEST_SA = get_secret("KB_INGEST_SA")
        
        # Decode Pub/Sub message
        # CloudEvent data structure for Pub/Sub: cloud_event.data contains the Pub/Sub message
        if cloud_event.data:
            if isinstance(cloud_event.data, dict):
                # Standard Pub/Sub format via CloudEvent
                if "message" in cloud_event.data:
                    # Pub/Sub message wrapped in CloudEvent
                    message_data = cloud_event.data["message"].get("data", "")
                    if message_data:
                        if isinstance(message_data, str):
                            message = base64.b64decode(message_data).decode("utf-8")
                        else:
                            message = base64.b64decode(message_data).decode("utf-8")
                    attributes = cloud_event.data["message"].get("attributes", {})
                elif "data" in cloud_event.data:
                    # Direct data field
                    message_data = cloud_event.data["data"]
                    if isinstance(message_data, str):
                        try:
                            message = base64.b64decode(message_data).decode("utf-8")
                        except:
                            message = message_data
                    else:
                        message = json.dumps(message_data)
                    attributes = cloud_event.attributes or {}
                else:
                    # Try to use data as JSON directly
                    message = json.dumps(cloud_event.data)
                    attributes = cloud_event.attributes or {}
            elif isinstance(cloud_event.data, (str, bytes)):
                # Data is a string or bytes
                if isinstance(cloud_event.data, bytes):
                    message = cloud_event.data.decode("utf-8")
                else:
                    try:
                        message = base64.b64decode(cloud_event.data).decode("utf-8")
                    except:
                        message = cloud_event.data
                attributes = cloud_event.attributes or {}
            else:
                # Fallback: serialize data to JSON
                message = json.dumps(cloud_event.data) if cloud_event.data else "{}"
                attributes = cloud_event.attributes or {}
        else:
            # No data, use empty message
            message = "{}"
            attributes = cloud_event.attributes or {}
        
        # Process the message using the shared processing function
        return _process_message(message, attributes)
        
    except Exception as error:
        print(f"Error processing Pub/Sub message: {error}")
        
        # Log the message that caused the error for debugging
        try:
            parsed_message = json.loads(message)
            print(f"Decoded message: {json.dumps(parsed_message, indent=2)}")
            print(f"Message attributes: {attributes}")
        except:
            print(f"Failed to parse message: {message}")
        
        # Return error result
        error_result = ProcessingResult(
            success=False,
            filename=parsed_message.get("filename", "unknown") if 'parsed_message' in locals() else "unknown",
            error=str(error)
        )
        
        # Re-raise for Cloud Functions to handle
        raise Exception(f"Failed to process Pub/Sub message: {str(error)}")


@functions_framework.http
def process_txt_ingest_topic_message_http(request: Request):
    """
    HTTP-triggered handler for local testing.
    This mimics the Pub/Sub message format for local development.
    """
    message = "{}"
    attributes = {}
    
    try:
        # Load secrets from Google Secret Manager
        EnvironmentVariables.EMBEDDINGS_API_URL = get_secret("EMBEDDINGS_API_URL")
        EnvironmentVariables.PINECONE_API_KEY = get_secret("PINECONE_API_KEY")
        EnvironmentVariables.PINECONE_ALL_MINILM_L6_V2_INDEX = get_secret("PINECONE_ALL_MINILM_L6_V2_INDEX")
        EnvironmentVariables.KB_INGEST_SA = get_secret("KB_INGEST_SA")
        
        # Parse HTTP request body
        if request.is_json:
            body = request.get_json()
        else:
            body = json.loads(request.data.decode('utf-8'))
        
        print("Detected HTTP trigger for local testing.")
        print(f"Request body: {json.dumps(body, indent=2)}")
        
        # Extract message from HTTP body (mimicking Pub/Sub format)
        if "data" in body:
            # Base64-encoded data (Pub/Sub format)
            message_data = body["data"]
            if isinstance(message_data, str):
                try:
                    message = base64.b64decode(message_data).decode("utf-8")
                except:
                    message = message_data
            else:
                message = json.dumps(message_data)
        elif "message" in body and "data" in body["message"]:
            # Nested Pub/Sub format
            message_data = body["message"]["data"]
            if isinstance(message_data, str):
                try:
                    message = base64.b64decode(message_data).decode("utf-8")
                except:
                    message = message_data
            else:
                message = json.dumps(message_data)
            attributes = body.get("attributes", {})
        else:
            # Direct JSON message
            message = json.dumps(body)
            attributes = body.get("attributes", {})
        
        # Process the message using the shared processing function
        result = _process_message(message, attributes)
        
        # Convert result to dictionary for JSON serialization
        result_dict = {
            "success": result.success,
            "filename": result.filename,
            "total_chunks_created": result.total_chunks_created,
            "successful_uploads": result.successful_uploads,
            "failed_uploads": result.failed_uploads,
            "file_size_bytes": result.file_size_bytes,
            "error": result.error
        }
        
        return {"status": "success", "result": result_dict}, 200
        
    except Exception as error:
        print(f"Error processing HTTP request: {error}")
        
        # Log the message that caused the error for debugging
        try:
            parsed_message = json.loads(message)
            print(f"Decoded message: {json.dumps(parsed_message, indent=2)}")
            print(f"Message attributes: {attributes}")
        except:
            print(f"Failed to parse message: {message}")
        
        return {"status": "error", "error": str(error)}, 500

