# TLDR

Cloud Function for ingesting .txt and .md files into a Pinecone Vector DB (Python implementation)

## Overview

This is a Python implementation of the Google Cloud Function that processes events published to a Google Pub/Sub topic. It downloads text/markdown files from Google Cloud Storage, processes them into chunks, generates embeddings, and stores them in Pinecone.

## Project Structure

```
.
├── main.py                          # Main entry point for the Cloud Function
├── helpers/                         # Helper modules
│   ├── __init__.py
│   ├── gcs.py                       # Google Cloud Storage operations
│   ├── text_processor.py           # Text/markdown file processing
│   ├── pinecone_helper.py          # Pinecone vector database operations
│   ├── get_secret.py                # Google Secret Manager integration
│   └── embedding.py                 # Embedding API client
├── singletons/                      # Singleton modules
│   ├── __init__.py
│   └── environment_variables.py     # Environment variables storage
├── requirements.txt                 # Python dependencies
├── .gcloudignore                    # Files to exclude from deployment
└── README.md                        # This file
```

## Prerequisites

- Python 3.9 or higher
- Google Cloud SDK (`gcloud`) installed and configured
- Access to Google Cloud project with the following APIs enabled:
  - Cloud Functions API
  - Cloud Pub/Sub API
  - Cloud Storage API
  - Secret Manager API

## Setup

1. **Install dependencies locally (for testing):**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up a Pub/Sub topic:**
   ```bash
   gcloud pubsub topics create txt-ingest-topic
   ```
   Verify topic was created: https://console.cloud.google.com/cloudpubsub/topic/list

3. **Ensure required secrets exist in Google Secret Manager:**
   - `EMBEDDINGS_API_URL`
   - `PINECONE_API_KEY`
   - `PINECONE_ALL_MINILM_L6_V2_INDEX`
   - `KB_INGEST_SA` (Service account JSON key, base64-encoded)

## How to Run Locally

1. **Install functions-framework:**
   ```bash
   pip install functions-framework
   ```

2. **Run the function locally:**
   ```bash
   functions-framework --target=process_txt_ingest_topic_message --debug
   ```

3. **Test with cURL:**
   ```bash
   curl -X POST http://localhost:8080/ \
     -H "Content-Type: application/json" \
     -d '{
       "data": {
         "message": {
           "data": "'$(echo -n '{"action":"process","key":"value"}' | base64)'",
           "attributes": {
             "exampleAttribute": "exampleValue"
           }
         }
       }
     }'
   ```

## Deployment

### Deploy to Google Cloud Functions (Gen 2)

```bash
# Make sure Cloud Functions API is enabled
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Deploy the function
gcloud functions deploy process-txt-ingest-topic-message \
  --gen2 \
  --runtime=python311 \
  --region=us-east1 \
  --source=. \
  --entry-point=process_txt_ingest_topic_message \
  --trigger-topic=txt-ingest-topic \
  --memory=1GB \
  --timeout=540s \
  --max-instances=10
```

### Deploy with Environment Variables (if needed)

```bash
gcloud functions deploy process-txt-ingest-topic-message-python \
  --gen2 \
  --runtime=python311 \
  --region=us-east1 \
  --source=. \
  --entry-point=process_txt_ingest_topic_message \
  --trigger-topic=txt-ingest-topic \
  --memory=1GB \
  --timeout=540s \
  --set-env-vars KEY=VALUE
```

## Testing

### Publish a test message to the Pub/Sub topic:

```bash
gcloud pubsub topics publish txt-ingest-topic \
  --message='{
    "filename": "test.txt",
    "gcs_bucket": "your-bucket-name",
    "gcs_file_path": "path/to/test.txt",
    "file_size": 1024,
    "content_type": "text/plain",
    "user_id": "test-user",
    "user_email": "test@example.com",
    "namespace": "reranking",
    "upload_timestamp": "2024-01-01T00:00:00Z",
    "processing_status": "pending",
    "jwt": "your-jwt-token"
  }'
```

### View logs:

```bash
# Tail logs in real-time
gcloud functions logs tail process-txt-ingest-topic-message --region=us-east1

# Read recent logs
gcloud functions logs read process-txt-ingest-topic-message --region=us-east1 --limit=50
```

## Supported File Types

The cloud function supports processing:

* **Text files** (.txt): Processed with YAML metadata parsing and text chunking
* **Markdown files** (.md): Processed with YAML front matter parsing and text chunking

### Text/Markdown Processing Features

* **YAML Front Matter**: Files can include metadata at the top delimited by `---`
* **Automatic Chunking**: Text is automatically split into chunks with configurable size (default: 200 words) and overlap (default: 50 words)
* **Metadata Preservation**: File metadata is preserved and attached to each chunk
* **Embedding Generation**: Each chunk is processed to generate vector embeddings via the embedding API

### Example Text File Format

```yaml
---
video_title: "What is Ollama?"
video_url: "https://www.youtube.com/watch/glkQIUTCAK4"
tags:
  - tutorial
  - ollama
  - ai
---

Content starts here...
```

## Message Format

The Pub/Sub message should be a JSON object with the following structure:

```json
{
  "filename": "example.txt",
  "gcs_bucket": "my-bucket",
  "gcs_file_path": "path/to/example.txt",
  "file_size": 1024,
  "content_type": "text/plain",
  "user_id": "user123",
  "user_email": "user@example.com",
  "namespace": "reranking",
  "upload_timestamp": "2024-01-01T00:00:00Z",
  "processing_status": "pending",
  "jwt": "your-jwt-token-here"
}
```

### Required Fields:
- `filename`: Name of the file (must end with .txt or .md)
- `gcs_bucket`: Google Cloud Storage bucket name
- `gcs_file_path`: Path to the file within the bucket
- `jwt`: JWT token for authenticating with the embedding API

### Optional Fields:
- `namespace`: Pinecone namespace (defaults to "reranking")
- `file_size`: Size of the file in bytes
- `content_type`: MIME type of the file
- `user_id`: ID of the user uploading the file
- `user_email`: Email of the user uploading the file
- `upload_timestamp`: ISO timestamp of when the file was uploaded
- `processing_status`: Current processing status

## Differences from Node.js Version

This Python implementation maintains the same functionality as the original Node.js/TypeScript version:

- ✅ Same Pub/Sub message format
- ✅ Same file processing logic (chunking, metadata parsing)
- ✅ Same Pinecone integration
- ✅ Same embedding API integration
- ✅ Same error handling and logging

The main differences are:
- Uses Python's `functions-framework` instead of Node.js `@google-cloud/functions-framework`
- Uses Python's `google-cloud-*` libraries instead of Node.js equivalents
- Uses Python's `pinecone-client` library instead of `@pinecone-database/pinecone`
- Uses Python's `requests` library instead of `axios`

## Troubleshooting

### Common Issues

1. **Secret Manager errors**: Ensure the Cloud Function's service account has the `secretmanager.secretAccessor` role
2. **GCS access errors**: Ensure the service account has access to the GCS bucket
3. **Pinecone connection errors**: Verify the Pinecone API key and index name are correct
4. **Embedding API errors**: Check that the JWT token is valid and the embedding API is accessible

### Debugging

Enable debug logging by setting the `FUNCTION_DEBUG` environment variable or check Cloud Function logs:

```bash
gcloud functions logs read process-txt-ingest-topic-message --region=us-east1 --limit=100
```

## License

ISC

