"""
Helper functions for processing text and markdown files.
"""
import hashlib
import time
from typing import Dict, List, Tuple, Any
from helpers.embedding import fetch_embedding
from helpers.pinecone_helper import VectorData


def parse_metadata_from_file(text_content: str) -> Tuple[Dict[str, str], str]:
    """
    Parse YAML front matter metadata from text content.
    
    Args:
        text_content: Full text content of the file
    
    Returns:
        Tuple of (metadata dictionary, content without metadata)
    """
    metadata: Dict[str, str] = {}
    lines = text_content.split('\n')
    content_lines: List[str] = []
    
    # Check if file starts with YAML front matter (---)
    if lines and lines[0].strip() == '---':
        # Find the end of YAML section
        yaml_end_index = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                yaml_end_index = i
                break
        
        if yaml_end_index > 0:
            # Extract YAML content
            yaml_content = '\n'.join(lines[1:yaml_end_index])
            
            try:
                # Simple YAML parsing for basic key-value pairs
                yaml_lines = yaml_content.split('\n')
                for line in yaml_lines:
                    colon_index = line.find(':')
                    if colon_index > 0:
                        key = line[:colon_index].strip()
                        value = line[colon_index + 1:].strip()
                        
                        # Remove quotes if present
                        if ((value.startswith('"') and value.endswith('"')) or
                            (value.startswith("'") and value.endswith("'"))):
                            value = value[1:-1]
                        
                        metadata[key] = value
                
                # Content starts after the second ---
                content_lines.extend(lines[yaml_end_index + 1:])
                
            except Exception as error:
                print(f"Warning: Failed to parse YAML metadata: {error}")
                # If YAML parsing fails, treat the whole file as content
                content_lines.extend(lines)
        else:
            # No closing --- found, treat as content
            content_lines.extend(lines)
    else:
        # No YAML front matter, treat as content
        content_lines.extend(lines)
    
    content_without_metadata = '\n'.join(content_lines)
    return metadata, content_without_metadata


def prepend_metadata_to_chunk(
    chunk: str,
    chunk_index: int,
    total_chunks: int,
    file_metadata: Dict[str, str],
    filename: str
) -> str:
    """
    Prepend metadata to a chunk with additional chunk-specific metadata.
    
    Args:
        chunk: The text chunk
        chunk_index: Zero-based index of the chunk
        total_chunks: Total number of chunks
        file_metadata: Metadata from the file's YAML front matter
        filename: Name of the source file
    
    Returns:
        Chunk with YAML front matter prepended
    """
    # Create chunk-specific metadata
    chunk_metadata = {
        "chunk_number": f"{chunk_index + 1} of {total_chunks}",  # 1-based for readability
        "filename": filename,
        "upload_timestamp_in_unix": str(int(time.time()))
    }
    
    # Combine file metadata with chunk metadata
    combined_metadata = {**file_metadata, **chunk_metadata}
    
    # Convert to YAML-like format
    yaml_content = '\n'.join([f"{key}: {value}" for key, value in combined_metadata.items()])
    
    # Create the final chunk with YAML front matter
    final_chunk = f"---\n{yaml_content}\n---\n\n{chunk}"
    
    return final_chunk


def chunk_text_by_tokens(text: str, chunk_size: int = 200, overlap: int = 50) -> List[str]:
    """
    Simple text chunking by approximate token count (words).
    
    Args:
        text: Text to chunk
        chunk_size: Number of words per chunk (default: 200)
        overlap: Number of overlapping words between chunks (default: 50)
    
    Returns:
        List of text chunks
    """
    words = text.split()
    chunks: List[str] = []
    i = 0
    
    while i < len(words):
        # Take chunk_size words
        chunk_words = words[i:i + chunk_size]
        chunk_text = ' '.join(chunk_words)
        chunks.append(chunk_text)
        
        # Move forward by chunk_size - overlap
        i += chunk_size - overlap
        
        # If we're near the end, just take the remaining words
        if i + chunk_size >= len(words):
            if i < len(words):
                remaining_words = words[i:]
                remaining_text = ' '.join(remaining_words)
                if remaining_text.strip():  # Only add if not empty
                    chunks.append(remaining_text)
            break
    
    return chunks


def generate_embedding_for_chunk(
    chunk: str,
    chunk_index: int,
    filename: str,
    jwt: str,
    file_metadata: Dict[str, str] = None,
    gcs_bucket: str = None,
    gcs_file_path: str = None
) -> VectorData | None:
    """
    Generate embedding for a single chunk and prepare vector data for storage.
    
    Args:
        chunk: Text chunk to process
        chunk_index: Zero-based index of the chunk
        filename: Name of the source file
        jwt: JWT token for embedding API
        file_metadata: Optional file metadata from YAML front matter
    
    Returns:
        VectorData object or None if processing failed
    """
    try:
        # Skip empty chunks
        if not chunk.strip():
            return None
        
        # Get embedding for the chunk
        embedding = fetch_embedding(jwt, chunk)
        
        if not embedding or len(embedding) == 0:
            raise ValueError("Failed to get embedding from API")
        
        # Create unique ID for the vector
        chunk_id_content = f"{filename}_{chunk_index + 1}_{chunk[:50]}"
        chunk_id = hashlib.sha256(chunk_id_content.encode()).hexdigest()
        
        # Prepare base metadata
        metadata: Dict[str, Any] = {
            "filename": filename,
            "chunkId": chunk_index + 1,  # 1-based for simplicity and intuition
            "content": chunk,
            "chunkSizeTokens": len(chunk.split()),  # Approximate token count
            "uploadTimestamp": str(int(time.time() * 1000)),
            "chunkNumber": chunk_index + 1,
            "totalChunks": 0  # Will be set later
        }

        # Provider-agnostic pointer back to the original source document
        # (Pinecone rejects nulls, so only set keys we actually have).
        if gcs_bucket or gcs_file_path:
            metadata["storage_provider"] = "gcs"
        if gcs_bucket:
            metadata["storage_bucket"] = gcs_bucket
        if gcs_file_path:
            metadata["storage_path"] = gcs_file_path

        # Add file metadata if available
        if file_metadata:
            # Prefix file metadata keys to avoid conflicts
            for key, value in file_metadata.items():
                metadata[f"file_{key}"] = value
        
        # Prepare vector data
        vector_data = VectorData(
            id=chunk_id,
            values=embedding,
            metadata=metadata
        )
        
        return vector_data
    except Exception as error:
        print(f"Error processing chunk {chunk_index}: {error}")
        return None


def process_text_file(
    content: str,
    filename: str,
    jwt: str,
    chunk_size: int = 200,
    overlap: int = 50,
    gcs_bucket: str = None,
    gcs_file_path: str = None
) -> Dict[str, Any]:
    """
    Process a single text/markdown file: validate, chunk, and prepare for upload.
    
    Args:
        content: File content as string
        filename: Name of the file
        jwt: JWT token for embedding API
        chunk_size: Number of words per chunk (default: 200)
        overlap: Number of overlapping words between chunks (default: 50)
    
    Returns:
        Dictionary with 'vectors', 'successful_chunks', and 'failed_chunks'
    """
    try:
        # Validate file type
        if not filename.lower().endswith('.txt') and not filename.lower().endswith('.md'):
            raise ValueError("Only .txt and .md files are supported")
        
        if not content.strip():
            raise ValueError("File is empty")
        
        # Parse metadata from the file
        metadata, content_without_metadata = parse_metadata_from_file(content)
        
        # Log metadata if found
        if metadata:
            print(f"Found YAML front matter in {filename}:")
            for key, value in metadata.items():
                print(f"  {key}: {value}")
        else:
            print(f"No YAML front matter found in {filename}")
        
        # Chunk the text
        raw_chunks = chunk_text_by_tokens(content_without_metadata, chunk_size, overlap)
        
        if not raw_chunks:
            raise ValueError("No valid chunks created from file")
        
        # Prepend metadata to each chunk
        chunks_with_metadata: List[str] = []
        for i in range(len(raw_chunks)):
            chunk_with_metadata = prepend_metadata_to_chunk(
                raw_chunks[i], i, len(raw_chunks), metadata, filename
            )
            chunks_with_metadata.append(chunk_with_metadata)
        
        # Process chunks
        print(f"Processing {len(chunks_with_metadata)} chunks for {filename}...")
        
        vectors: List[VectorData] = []
        successful_chunks = 0
        failed_chunks = 0
        
        for i in range(len(chunks_with_metadata)):
            print(f"Processing chunk {i + 1} of {len(chunks_with_metadata)} for {filename}")
            
            vector_data = generate_embedding_for_chunk(
                chunks_with_metadata[i], i, filename, jwt, metadata,
                gcs_bucket=gcs_bucket, gcs_file_path=gcs_file_path
            )
            
            if vector_data:
                # Add total_chunks to metadata
                vector_data.metadata["totalChunks"] = len(chunks_with_metadata)
                vectors.append(vector_data)
                successful_chunks += 1
            else:
                failed_chunks += 1
        
        return {
            "vectors": vectors,
            "successful_chunks": successful_chunks,
            "failed_chunks": failed_chunks
        }
        
    except Exception as error:
        raise Exception(f"Failed to process text file: {str(error)}")

