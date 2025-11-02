import os
import time
import hashlib
from pathlib import Path
import openai
from openai import AsyncOpenAI, OpenAIError, APIError, AuthenticationError, RateLimitError
import click
import logging
from dotenv import load_dotenv
import traceback
from typing import Optional, Tuple, List
import asyncio

# --- Configuration ---
load_dotenv()
ASSISTANT_MODEL = "gpt-4o-mini"
POLL_INTERVAL_S = 5
FILE_PROCESS_TIMEOUT_S = 600 # 10 minutes
BATCH_PROCESS_TIMEOUT_S = 1800 # 30 minutes
RUN_TIMEOUT_S = 300 # 5 minutes
SUPPORTED_EXTENSIONS = {".txt", ".json", ".md", ".pdf", ".py", ".html", ".csv", ".tsv", ".rtf", ".xml"}
MAX_FILES_IN_BATCH = 450
FILE_PREFIX = "FileStore"
FOLDER_PREFIX = "FolderStore"

logger = logging.getLogger(__name__)

# --- Helper Function (remains synchronous) ---
def get_file_hash(filepath: Path) -> str:
    """Generates a SHA256 hash for a file's content."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as file:
            while True:
                chunk = file.read(8192) # Read in chunks
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except IOError as e:
        logger.error(f"Error reading file {filepath} for hashing: {e}")
        raise # Re-raise the error to be handled upstream

# ---> Helper to sanitize names for OpenAI resources <---
def sanitize_openai_name(name: str) -> str:
    """Sanitizes a string for use as an OpenAI resource name (max 256 chars)."""
    # Replace potentially problematic characters (simplistic approach)
    sanitized = ''.join(c if c.isalnum() or c in ['-', '_', '.'] else '_' for c in name)
    # Enforce length limit
    return sanitized[:256]

# --- Main Class ---
class OpenAIVectorQA:
    """
    Manages Q&A over files or folders using OpenAI Files, Vector Stores, and Assistants API v2 (Async).
    """
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables.")
        try:
            self.client = AsyncOpenAI(api_key=self.api_key, timeout=60.0, max_retries=3)
            logger.info("OpenAI Async client configured.")
        except Exception as e:
            logger.error(f"CRITICAL ERROR: Failed to initialize OpenAI client: {e}")
            raise ValueError(f"Failed to initialize OpenAI client: {e}")

        self.vector_store_prefix = "qa_vs_"
        self.assistant_prefix = "qa_as_"

    # ---> Renamed and adapted for single file <---
    async def ensure_assistant_ready_for_file(self, file_path: Path) -> Optional[str]:
        """
        Ensures a Vector Store and Assistant exist for a SINGLE file and are ready for Q&A.
        Returns the Assistant ID if successful, otherwise None.
        """
        click.echo(f"\n🔄 Preparing OpenAI resources for file: {file_path.name}...")
        if not file_path.is_file():
            click.echo(f"❌ Error: Path is not a valid file: {file_path}", err=True)
            return None

        try:
            file_hash = get_file_hash(file_path)
            # ---> Use prefix and sanitized name <---
            resource_name = f"{FILE_PREFIX}-{sanitize_openai_name(file_path.stem)}-{file_hash[:8]}"
            logger.info(f"Generated resource name for file: {resource_name}")

            # 1. Find or Create Vector Store
            vector_store_id = await self._find_or_create_vector_store(resource_name)
            if not vector_store_id: return None # Error handled in helper

            # 2. Upload file and add to store (only if store is new - simplistic check)
            # A more robust check would involve listing files in the store if it exists.
            # For simplicity, we assume if the store exists, the file is already there.
            # This might fail if the store exists but file processing failed previously.
            store_info = await self.client.beta.vector_stores.retrieve(vector_store_id)
            # Check if the store is empty or just created (status might be 'completed' even if empty initially)
            # A better check might be store_info.file_counts.total == 0, but let's rely on name uniqueness for now.
            # We'll attempt to add the file if the store seems fresh or potentially empty.
            # A truly robust system needs better state tracking.

            # Let's try adding the file regardless and let OpenAI handle duplicates if the file ID is already there.
            # This simplifies logic but might involve redundant API calls if the file exists.
            file_id = await self._upload_file(file_path)
            if not file_id: return None # Error handled in helper

            # Add the single file to the store (this is idempotent if file_id already exists)
            click.echo(f"  ➕ Adding file {file_path.name} (ID: {file_id}) to Vector Store {vector_store_id}...")
            try:
                await self.client.beta.vector_stores.files.create(
                    vector_store_id=vector_store_id,
                    file_id=file_id
                )
                # Poll for the single file processing status
                if not await self._poll_vector_store_file_status(vector_store_id, file_id):
                    click.echo(f"❌ File {file_id} did not process successfully in the vector store.", err=True)
                    # Consider cleanup? For now, just return None.
                    return None
                click.echo(f"  ✅ File {file_id} processed in store.")
            except APIError as e:
                # Handle potential errors like file already being processed or store issues
                logger.error(f"API Error adding file {file_id} to store {vector_store_id}: {e.status_code} - {e.message}")
                click.echo(f"⚠️ Warning: Could not add file {file_id} to store (may already exist or be processing): {e.message}", err=True)
                # Attempt to continue, assuming the file might already be there and processed.
                # Check status again just in case.
                if not await self._poll_vector_store_file_status(vector_store_id, file_id, check_existing=True):
                     click.echo(f"❌ File {file_id} still not processed successfully.", err=True)
                     return None


            # 3. Find or Create Assistant linked to the store
            assistant_id = await self._find_or_create_assistant(resource_name, vector_store_id)
            if not assistant_id: return None # Error handled in helper

            click.echo(f"✅ Assistant ready (ID: {assistant_id}) for file: {file_path.name}")
            return assistant_id

        except AuthenticationError:
             logger.error("OpenAI Authentication Failed. Check API Key.")
             click.echo("❌ Error: OpenAI Authentication Failed. Check your API Key.", err=True)
             return None
        except APIError as e:
             logger.error(f"OpenAI API Error during setup: {e.status_code} - {e.message}")
             click.echo(f"❌ Error: OpenAI API Error during setup: {e.message}", err=True)
             return None
        except OpenAIError as e:
            logger.error(f"OpenAI Error during setup: {e}")
            click.echo(f"❌ Error: An OpenAI error occurred during setup: {e}", err=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error preparing assistant for file {file_path.name}: {e}\n{traceback.format_exc()}")
            click.echo(f"❌ An unexpected error occurred during setup: {e}", err=True)
            return None

    # ---> NEW method for handling folders <---
    async def ensure_assistant_ready_for_folder(self, folder_path: Path) -> Optional[str]:
        """
        Ensures a Vector Store and Assistant exist for ALL supported files within a FOLDER.
        Returns the Assistant ID if successful, otherwise None.
        """
        click.echo(f"\n🔄 Preparing OpenAI resources for folder: {folder_path.name}...")
        if not folder_path.is_dir():
            click.echo(f"❌ Error: Path is not a valid directory: {folder_path}", err=True)
            return None

        try:
            # 1. Scan folder for supported files
            files_to_process = []
            click.echo(f"  🔍 Scanning folder for supported file types ({', '.join(SUPPORTED_EXTENSIONS)})...")
            for item in folder_path.rglob('*'): # Use rglob for recursive search
                if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files_to_process.append(item)

            if not files_to_process:
                click.echo("❌ No supported files found in the specified folder.", err=True)
                return None

            if len(files_to_process) > MAX_FILES_IN_BATCH:
                 click.echo(f"⚠️ Warning: Found {len(files_to_process)} files, exceeding the limit of {MAX_FILES_IN_BATCH}. Processing the first {MAX_FILES_IN_BATCH} files.", err=True)
                 files_to_process = files_to_process[:MAX_FILES_IN_BATCH]

            click.echo(f"  📂 Found {len(files_to_process)} files to process.")

            # Generate a resource name based on the folder
            # Using hash of folder name for more uniqueness, less likely to collide
            folder_hash = hashlib.sha256(folder_path.name.encode()).hexdigest()[:8]
            resource_name = f"{FOLDER_PREFIX}-{sanitize_openai_name(folder_path.name)}-{folder_hash}"
            logger.info(f"Generated resource name for folder: {resource_name}")

            # 2. Find or Create Vector Store
            vector_store_id = await self._find_or_create_vector_store(resource_name)
            if not vector_store_id: return None

            # 3. Upload files and add to store (Batch Process)
            # Simplistic check: Assume if store exists, files *might* be there.
            # A robust solution would list files in the store and compare.
            # For now, we will re-upload and create a new batch if the store exists,
            # letting OpenAI handle potential duplicate file processing internally.
            uploaded_file_ids = []
            click.echo(f"  ⬆️ Uploading {len(files_to_process)} files to OpenAI...")
            upload_tasks = [self._upload_file(f) for f in files_to_process]
            results = await asyncio.gather(*upload_tasks, return_exceptions=True)

            successful_uploads = 0
            for i, result in enumerate(results):
                if isinstance(result, str): # Successful upload returns file_id (string)
                    uploaded_file_ids.append(result)
                    successful_uploads += 1
                else: # An exception occurred during upload
                    click.echo(f"  ❌ Failed to upload {files_to_process[i].name}: {result}", err=True)
                    logger.error(f"Failed to upload {files_to_process[i].name}: {result}")

            if not uploaded_file_ids:
                click.echo("❌ No files were successfully uploaded. Cannot proceed.", err=True)
                # Consider deleting the potentially empty vector store?
                # await self.cleanup_resources(vector_store_id=vector_store_id)
                return None

            click.echo(f"  ✅ Successfully uploaded {successful_uploads}/{len(files_to_process)} files.")

            # Create a file batch
            if uploaded_file_ids:
                click.echo(f"  ➕ Creating file batch for {len(uploaded_file_ids)} files in Vector Store {vector_store_id}...")
                try:
                    file_batch = await self.client.beta.vector_stores.file_batches.create(
                        vector_store_id=vector_store_id,
                        file_ids=uploaded_file_ids
                    )
                    click.echo(f"  ⏳ Batch created (ID: {file_batch.id}). Polling for completion (this may take time)...")
                    # Poll for batch completion
                    if not await self._poll_batch_status(vector_store_id, file_batch.id):
                        click.echo(f"❌ File batch {file_batch.id} did not complete successfully.", err=True)
                        # Consider cleanup?
                        return None
                    click.echo(f"  ✅ File batch {file_batch.id} processed.")
                except APIError as e:
                    logger.error(f"API Error creating file batch for store {vector_store_id}: {e.status_code} - {e.message}")
                    click.echo(f"❌ Error creating file batch: {e.message}", err=True)
                    return None


            # 4. Find or Create Assistant linked to the store
            assistant_id = await self._find_or_create_assistant(resource_name, vector_store_id)
            if not assistant_id: return None

            click.echo(f"✅ Assistant ready (ID: {assistant_id}) for folder: {folder_path.name}")
            return assistant_id

        except AuthenticationError:
             logger.error("OpenAI Authentication Failed. Check API Key.")
             click.echo("❌ Error: OpenAI Authentication Failed. Check your API Key.", err=True)
             return None
        except APIError as e:
             logger.error(f"OpenAI API Error during folder setup: {e.status_code} - {e.message}")
             click.echo(f"❌ Error: OpenAI API Error during folder setup: {e.message}", err=True)
             return None
        except OpenAIError as e:
            logger.error(f"OpenAI Error during folder setup: {e}")
            click.echo(f"❌ Error: An OpenAI error occurred during folder setup: {e}", err=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error preparing assistant for folder {folder_path.name}: {e}\n{traceback.format_exc()}")
            click.echo(f"❌ An unexpected error occurred during folder setup: {e}", err=True)
            return None


    # ---> Generic helper to find/create store <---
    async def _find_or_create_vector_store(self, resource_name: str) -> Optional[str]:
        """Finds a vector store by name or creates a new one."""
        logger.info(f"Searching for existing Vector Store named '{resource_name}'...")
        try:
            stores = await self.client.beta.vector_stores.list(limit=100)
            existing_store = next((s for s in stores.data if s.name == resource_name), None)

            if existing_store:
                # Basic check for usability (status exists and is not failed/expired)
                if hasattr(existing_store, 'status') and existing_store.status in ['failed', 'expired', 'cancelled']:
                     click.echo(f"  ⚠️ Found existing store '{resource_name}' but its status is '{existing_store.status}'. Attempting to delete and recreate.", err=True)
                     logger.warning(f"Deleting unusable store {existing_store.id} with status {existing_store.status}")
                     await self.cleanup_resources(vector_store_id=existing_store.id)
                     existing_store = None # Force recreation
                else:
                    click.echo(f"  ✅ Found existing Vector Store: {existing_store.id}")
                    return existing_store.id

            # If not found or was unusable, create a new one
            click.echo(f"  ℹ️ No suitable existing store found. Creating new Vector Store: '{resource_name}'...")
            new_store = await self.client.beta.vector_stores.create(name=resource_name)
            click.echo(f"  ✅ Created Vector Store: {new_store.id}")
            return new_store.id

        except APIError as e:
            logger.error(f"API Error finding/creating vector store '{resource_name}': {e.status_code} - {e.message}")
            click.echo(f"❌ Error finding/creating vector store: {e.message}", err=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error finding/creating vector store '{resource_name}': {e}\n{traceback.format_exc()}")
            click.echo(f"❌ Unexpected error with vector store: {e}", err=True)
            return None

    # ---> Generic helper to find/create assistant <---
    async def _find_or_create_assistant(self, resource_name: str, vector_store_id: str) -> Optional[str]:
        """Finds an assistant by name or creates a new one linked to the vector store."""
        assistant_name = f"QA_{resource_name}" # Use distinct name for assistant
        logger.info(f"Searching for existing Assistant named '{assistant_name}'...")
        try:
            assistants = await self.client.beta.assistants.list(limit=100)
            existing_assistant = next((a for a in assistants.data if a.name == assistant_name), None)

            if existing_assistant:
                # Check if it's linked to the *correct* vector store
                # Assistants API v2 uses tool_resources.file_search.vector_store_ids
                current_vs_ids = []
                if existing_assistant.tool_resources and existing_assistant.tool_resources.file_search:
                    current_vs_ids = existing_assistant.tool_resources.file_search.vector_store_ids or []

                if vector_store_id in current_vs_ids:
                    click.echo(f"  ✅ Found existing Assistant: {existing_assistant.id} (linked to store {vector_store_id})")
                    return existing_assistant.id
                else:
                    click.echo(f"  ⚠️ Found existing Assistant '{assistant_name}' but it's not linked to the correct store {vector_store_id}. Creating new assistant.", err=True)
                    # We could update the assistant, but creating new is simpler for now
                    existing_assistant = None # Force recreation

            # Create new assistant
            click.echo(f"  ℹ️ Creating new Assistant '{assistant_name}' linked to store {vector_store_id}...")
            instructions = "You are a helpful assistant. Answer questions based ONLY on the context provided by the attached files. State if the answer cannot be found in the files. Be concise."
            new_assistant = await self.client.beta.assistants.create(
                name=assistant_name,
                instructions=instructions,
                model=ASSISTANT_MODEL,
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
            )
            click.echo(f"  ✅ Created Assistant: {new_assistant.id}")
            return new_assistant.id

        except APIError as e:
            logger.error(f"API Error finding/creating assistant '{assistant_name}': {e.status_code} - {e.message}")
            click.echo(f"❌ Error finding/creating assistant: {e.message}", err=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error finding/creating assistant '{assistant_name}': {e}\n{traceback.format_exc()}")
            click.echo(f"❌ Unexpected error with assistant: {e}", err=True)
            return None

    # ---> Reusable file upload helper <---
    async def _upload_file(self, file_path: Path) -> Optional[str]:
        """Uploads a single file to OpenAI and returns the file ID."""
        file_name = file_path.name
        try:
            click.echo(f"    📤 Uploading {file_name}...")
            logger.info(f"Attempting to upload file: {file_path}")

            # --- MODIFIED: Open file synchronously just for the upload ---
            with file_path.open("rb") as file_handle:
                file_object = await self.client.files.create(
                    file=file_handle, # Pass the synchronous file handle
                    purpose="assistants", # Vector stores use the 'assistants' purpose
                )

            # ---> Check if file_object has an ID <---
            if file_object and file_object.id:
                logger.info(f"Successfully uploaded file {file_name}, File ID: {file_object.id}")
                click.echo(f"    ✅ Uploaded {file_name} (ID: {file_object.id})")
                return file_object.id
            else:
                # This case might be less likely if an error wasn't raised, but good to handle
                logger.error(f"File upload for {file_name} returned an unexpected object: {file_object}")
                click.echo(f"    ❌ Failed to get File ID for {file_name} after upload.", err=True)
                return None

        # --- MODIFIED: Use the imported openai module for exception handling ---
        except openai.APIError as e:
            error_message = f"OpenAI API error uploading file {file_name}: {e}"
            logger.error(error_message, exc_info=True)
            click.echo(f"    ❌ {error_message}", err=True)
            return None
        except FileNotFoundError:
            error_message = f"File not found during upload: {file_path}"
            logger.error(error_message)
            click.echo(f"    ❌ {error_message}", err=True)
            return None
        except Exception as e:
            # Catch any other unexpected error
            error_message = f"Unexpected error uploading file {file_name}: {e}"
            logger.error(error_message, exc_info=True)
            traceback.print_exc()
            click.echo(f"    ❌ {error_message}", err=True)
            return None

    # ---> UPDATED Polling for single file status in a store <---
    async def _poll_vector_store_file_status(self, vector_store_id: str, file_id: str, check_existing: bool = False) -> bool:
        """Polls the status of a specific file within a vector store."""
        start_time = time.time()
        if not check_existing:
             click.echo(f"    ⏱️ Waiting for file {file_id} to be processed in store {vector_store_id}...")
        else:
             click.echo(f"    ⏱️ Checking status of existing file {file_id} in store {vector_store_id}...")

        while time.time() - start_time < FILE_PROCESS_TIMEOUT_S:
            try:
                vs_file = await self.client.beta.vector_stores.files.retrieve(
                    vector_store_id=vector_store_id,
                    file_id=file_id
                )
                status = vs_file.status
                logger.debug(f"File {file_id} status in store {vector_store_id}: {status}")

                if status == 'completed':
                    click.echo(f"    ✅ File {file_id} processing complete.")
                    return True
                elif status == 'failed':
                    last_error = getattr(vs_file, 'last_error', None)
                    error_message = getattr(last_error, 'message', 'Unknown error') if last_error else 'Unknown error'
                    click.echo(f"    ❌ File {file_id} processing failed: {error_message}", err=True)
                    logger.error(f"File {file_id} processing failed in store {vector_store_id}: {error_message}")
                    return False
                elif status == 'cancelled':
                     click.echo(f"    ❌ File {file_id} processing cancelled.", err=True)
                     logger.error(f"File {file_id} processing cancelled in store {vector_store_id}")
                     return False
                # Status 'in_progress', continue polling

            except APIError as e:
                # Handle 404 if the file isn't associated yet, wait a bit
                if e.status_code == 404 and not check_existing:
                    logger.warning(f"File {file_id} not found in store {vector_store_id} yet, possibly still associating...")
                # Handle rate limits
                elif isinstance(e, RateLimitError):
                     logger.warning(f"Rate limit hit polling file status for {file_id}. Waiting...")
                     await asyncio.sleep(POLL_INTERVAL_S * 2) # Longer wait on rate limit
                     continue # Skip the standard wait
                else:
                    logger.error(f"API Error polling file {file_id} status: {e.status_code} - {e.message}")
                    click.echo(f"    ⚠️ API Error polling file status: {e.message}", err=True)
                    # Decide whether to retry or fail - let's retry a few times implicitly via the loop
            except Exception as e:
                logger.error(f"Unexpected error polling file {file_id} status: {e}\n{traceback.format_exc()}")
                click.echo(f"    ⚠️ Unexpected error polling file status: {e}", err=True)
                # Decide whether to retry or fail

            await asyncio.sleep(POLL_INTERVAL_S)

        click.echo(f"    ❌ Timeout waiting for file {file_id} processing.", err=True)
        logger.error(f"Timeout waiting for file {file_id} processing in store {vector_store_id}")
        return False


    # ---> NEW Polling function for batch status <---
    async def _poll_batch_status(self, vector_store_id: str, batch_id: str) -> bool:
        """Polls the status of a file batch."""
        start_time = time.time()
        click.echo(f"    ⏱️ Polling batch {batch_id} status (Timeout: {BATCH_PROCESS_TIMEOUT_S}s)...")

        while time.time() - start_time < BATCH_PROCESS_TIMEOUT_S:
            try:
                batch_status = await self.client.beta.vector_stores.file_batches.retrieve(
                    vector_store_id=vector_store_id,
                    batch_id=batch_id
                )
                status = batch_status.status
                counts = batch_status.file_counts
                logger.debug(f"Batch {batch_id} status: {status}, Counts: {counts}")
                # Provide more detailed progress
                click.echo(f"\r    ⏱️ Batch Status: {status} [Completed: {counts.completed}, Failed: {counts.failed}, In Progress: {counts.in_progress}, Total: {counts.total}]", nl=False)

                if status == "completed":
                    click.echo("\n    ✅ Batch processing completed.") # Newline after final status
                    if counts.failed > 0:
                        click.echo(f"    ⚠️ Warning: {counts.failed} files failed during batch processing.", err=True)
                        # Optionally retrieve the batch files to list failed ones? More complex.
                    return True
                elif status in ["failed", "cancelled", "expired"]:
                    click.echo(f"\n    ❌ Batch processing did not complete successfully (Status: {status}).", err=True) # Newline
                    logger.error(f"Batch {batch_id} failed or was cancelled/expired. Status: {status}")
                    return False
                # Status 'in_progress', continue polling

            except RateLimitError as e:
                 logger.warning(f"Rate limit hit polling batch status for {batch_id}. Waiting...")
                 click.echo("\n    ⏳ Rate limit hit, pausing polling...", nl=False)
                 await asyncio.sleep(POLL_INTERVAL_S * 5) # Longer wait on rate limit
                 continue # Skip the standard wait
            except APIError as e:
                logger.error(f"API Error polling batch {batch_id} status: {e.status_code} - {e.message}")
                click.echo(f"\n    ⚠️ API Error polling batch status: {e.message}", err=True) # Newline
                # Decide whether to retry or fail
            except Exception as e:
                logger.error(f"Unexpected error polling batch {batch_id} status: {e}\n{traceback.format_exc()}")
                click.echo(f"\n    ⚠️ Unexpected error polling batch status: {e}", err=True) # Newline
                # Decide whether to retry or fail

            await asyncio.sleep(POLL_INTERVAL_S)

        click.echo(f"\n    ❌ Timeout waiting for batch {batch_id} processing.", err=True) # Newline
        logger.error(f"Timeout waiting for batch {batch_id} processing in store {vector_store_id}")
        return False


    # ---> ask_question remains largely the same, uses assistant_id <---
    async def ask_question(self, assistant_id: str, question: str) -> str:
        """Asks a question using the specified Assistant and returns the answer."""
        click.echo("  🤖 Creating thread and asking question...")
        try:
            # 1. Create a Thread
            thread = await self.client.beta.threads.create()
            logger.info(f"Created thread {thread.id} for assistant {assistant_id}")

            # 2. Add Message to Thread
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=question,
            )

            # 3. Create a Run
            run = await self.client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id,
                # Optional: Add instructions specific to this run if needed
                # instructions="Focus on financial data in your answer."
            )
            logger.info(f"Created run {run.id} for thread {thread.id}")
            click.echo(f"  ⏳ Run created (ID: {run.id}). Waiting for completion...")

            # 4. Poll Run Status
            start_time = time.time()
            while run.status in ['queued', 'in_progress', 'cancelling']:
                if time.time() - start_time > RUN_TIMEOUT_S:
                    click.echo("\n  ❌ Run timed out.", err=True)
                    logger.error(f"Run {run.id} timed out.")
                    # Attempt to cancel the run
                    try:
                        await self.client.beta.threads.runs.cancel(thread_id=thread.id, run_id=run.id)
                        logger.info(f"Attempted to cancel timed out run {run.id}")
                    except Exception as cancel_err:
                        logger.error(f"Error cancelling run {run.id}: {cancel_err}")
                    return "Assistant run timed out."

                await asyncio.sleep(POLL_INTERVAL_S)
                run = await self.client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                logger.debug(f"Run {run.id} status: {run.status}")
                click.echo(f"\r  ⏳ Run Status: {run.status}...", nl=False) # Update status inline

            click.echo(f"\n  🏁 Run finished with status: {run.status}") # Newline after final status

            if run.status == 'completed':
                # 5. Retrieve Messages
                messages = await self.client.beta.threads.messages.list(
                    thread_id=thread.id, order="desc" # Get newest first
                )
                # Find the first assistant message(s) in the latest run
                assistant_messages_content = []
                for msg in messages.data:
                    if msg.run_id == run.id and msg.role == 'assistant':
                        for content_block in msg.content:
                             if content_block.type == 'text':
                                 assistant_messages_content.append(content_block.text.value)
                             elif content_block.type == 'image_file':
                                 # Handle image case if needed, e.g., log or mention it
                                 assistant_messages_content.append("[Assistant sent an image - content not displayed]")
                                 logger.info(f"Assistant sent image: {content_block.image_file.file_id}")

                        # Once we find the message(s) from our run, we can stop searching older messages
                        if assistant_messages_content:
                            break

                if assistant_messages_content:
                    # Join multiple message parts if the assistant broke its response up
                    final_answer = "\n".join(reversed(assistant_messages_content)) # Put parts back in order
                    click.echo("✅ Assistant response received.")
                    return final_answer
                else:
                    click.echo("⚠️ Assistant completed but no response message was found.", err=True)
                    logger.warning(f"No assistant message found in thread {thread.id} for run {run.id}")
                    return "Assistant did not provide a text response."
            elif run.status == 'failed':
                 last_error = getattr(run, 'last_error', None)
                 error_message = getattr(last_error, 'message', 'Unknown error') if last_error else 'Unknown error'
                 click.echo(f"❌ Assistant run failed: {error_message}", err=True)
                 logger.error(f"Run {run.id} failed: {error_message}")
                 return f"Assistant run failed: {error_message}"
            elif run.status == 'requires_action':
                 # This shouldn't happen with only file_search, but handle defensively
                 click.echo("❌ Assistant run requires unexpected action.", err=True)
                 logger.error(f"Run {run.id} requires action, which is not handled.")
                 return "Assistant run requires an unexpected action."
            else: # cancelled, expired
                 click.echo(f"❌ Assistant run ended with status: {run.status}", err=True)
                 logger.error(f"Run {run.id} ended with status: {run.status}")
                 return f"Assistant run ended with status: {run.status}"


        except AuthenticationError:
             logger.error(f"OpenAI Authentication Failed during Q&A for assistant {assistant_id}. Check API Key.")
             click.echo("❌ Error during Q&A: Authentication Failed.", err=True)
             return "An authentication error occurred. Check your API Key."
        except APIError as e:
             logger.error(f"OpenAI API Error during Q&A for assistant {assistant_id}: {e.status_code} - {e.message}")
             click.echo(f"❌ Error during Q&A (API Error): {e.message}", err=True)
             return f"An API error occurred: {e.message}"
        except OpenAIError as e:
            logger.error(f"OpenAI Error during Q&A with assistant {assistant_id}: {e}")
            click.echo(f"❌ An OpenAI error occurred during Q&A: {e}", err=True)
            return f"An OpenAI error occurred: {e}"
        except Exception as e:
            logger.error(f"Unexpected error during Q&A with assistant {assistant_id}: {e}\n{traceback.format_exc()}")
            click.echo(f"❌ An unexpected error occurred during Q&A: {e}", err=True)
            return f"An unexpected error occurred: {e}"

    # ---> cleanup_resources remains the same (already async) <---
    async def cleanup_resources(self, assistant_id: Optional[str] = None, vector_store_id: Optional[str] = None):
        """(Optional) Deletes the specified assistant and vector store (async)."""
        # Be cautious using this! Deletes resources permanently.
        if assistant_id:
            try:
                click.echo(f"Attempting to delete Assistant {assistant_id}...")
                await self.client.beta.assistants.delete(assistant_id)
                click.echo(f"  Assistant {assistant_id} deleted.")
            except Exception as e:
                click.echo(f"  Error deleting assistant {assistant_id}: {e}", err=True)
                logger.error(f"Error deleting assistant {assistant_id}: {e}")

        if vector_store_id:
            # Deleting a vector store also deletes associated files if they aren't attached elsewhere
            try:
                click.echo(f"Attempting to delete Vector Store {vector_store_id}...")
                await self.client.beta.vector_stores.delete(vector_store_id)
                click.echo(f"  Vector Store {vector_store_id} deleted.")
            except Exception as e:
                click.echo(f"  Error deleting vector store {vector_store_id}: {e}", err=True)
                logger.error(f"Error deleting vector store {vector_store_id}: {e}") 