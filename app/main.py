from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from . import models, schemas, crud
# LLM utilities moved to app/llm.py
from . import llm
from typing import List, Optional, Dict, Any # Added Optional, Dict, Any
from pydantic import BaseModel
try:
    import whisper  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    whisper = None

import os
import json
from pathlib import Path # Ensure Path is imported
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


# Pydantic model for model info, defined in main as it's specific to this API's responses
class ModelInfo(BaseModel):
    name: str
    size_mb: int
    is_downloaded: bool

app = FastAPI()

# Define allowed origins for CORS
origins = [
    "http://localhost:5173", # React frontend development server
    "http://localhost:3000", # Another common port for React dev server
    # Add other origins if needed, e.g., your production frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

router = APIRouter()

# Cache for loaded whisper models so they are downloaded only once
if whisper is not None:
    MODEL_CACHE: dict[str, whisper.Whisper] = {}
else:  # pragma: no cover - whisper not installed
    MODEL_CACHE: dict[str, object] = {}

# Whisper model sizes (approximate, from official sources)
WHISPER_MODEL_SIZES_MB = {
    "small.en": 244,
    "medium.en": 1420,
}

def get_whisper_cache_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".cache", "whisper")

def is_model_downloaded(model_name: str) -> bool:
    normalized_name = model_name.split('.')[0]
    # Special handling for 'large' which might be versioned like large-v3.pt
    # Whisper's load_model handles mapping 'large' to the correct versioned file.
    # For cache checking, we need to be a bit more specific or check common patterns.
    if normalized_name.startswith("large"):
        # Check for common large model file names like large.pt, large-v2.pt, large-v3.pt
        # This list might need updates if Whisper changes naming conventions significantly.
        possible_files = [f"{v}.pt" for v in ["large", "large-v2", "large-v3"]]
    else:
        possible_files = [f"{normalized_name}.pt"]

    cache_dir = Path(get_whisper_cache_dir())
    for f_name in possible_files:
        if (cache_dir / f_name).exists():
            logger.debug(f"Found cached model file: {cache_dir / f_name}")
            return True
    logger.debug(f"Model file for '{model_name}' (checked as {possible_files}) not found in {cache_dir}.")
    return False

# create database tables
Base.metadata.create_all(bind=engine)

# app.mount("/static", StaticFiles(directory="app/static"), name="static") # Temporarily commented out as app/static was removed for React frontend

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("app/static/index.html") as f:
        return HTMLResponse(f.read())


def get_model(name: str):
    """Load a Whisper model by name and cache it."""
    if whisper is None:
        raise HTTPException(status_code=500, detail="whisper not installed")
    model = MODEL_CACHE.get(name)
    if model is None:
        model = whisper.load_model(name)
        MODEL_CACHE[name] = model
    return model

@router.post("/tasks", response_model=schemas.TaskRead)
async def create_task_endpoint(task_data: schemas.TaskCreate, db: Session = Depends(get_db)):
    try:
        created_task_dict = crud.create_task(db, task_create_data=task_data)
        # crud.create_task now returns a dict, so we parse it into the response model
        return schemas.TaskRead(**created_task_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating task: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@router.get("/tasks", response_model=List[schemas.TaskRead])
async def get_tasks_from_latest_version(db: Session = Depends(get_db)):
    """Returns tasks from the latest version's snapshot."""
    latest_version = crud.get_latest_task_manager_version(db)
    if not latest_version:
        # If no versions exist yet (e.g., new database), return empty list.
        # The first task operation will create version 1.
        return []
    
    # snapshot_data is stored as List[Dict]. We need to parse them into TaskRead.
    # TaskSnapshotItem is compatible with TaskRead for instantiation here.
    tasks_from_snapshot = [schemas.TaskRead(**task_data) for task_data in latest_version.snapshot_data]
    return tasks_from_snapshot


@router.get("/versions", response_model=List[schemas.TaskManagerVersionInfo])
async def list_versions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lists available task manager versions (ID, version number, created_at)."""
    versions_orm = crud.list_task_manager_versions(db, skip=skip, limit=limit)
    return [schemas.TaskManagerVersionInfo.from_orm(v) for v in versions_orm]


@router.get("/versions/{version_number}/tasks", response_model=List[schemas.TaskSnapshotItem])
async def get_tasks_for_version(version_number: int, db: Session = Depends(get_db)):
    """Returns all tasks as they were in a specific historical version."""
    version = crud.get_task_manager_version(db, version_number=version_number)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found.")
    
    # snapshot_data is List[Dict], parse into TaskSnapshotItem
    tasks_from_snapshot = [schemas.TaskSnapshotItem(**task_data) for task_data in version.snapshot_data]
    return tasks_from_snapshot

@router.delete("/tasks/{task_id}", response_model=Dict[str, Any]) # Changed response model
async def delete_task_endpoint(task_id: int, base_version_number: Optional[int] = Query(None), db: Session = Depends(get_db)):
    try:
        deleted_task_dict = crud.delete_task(db, task_id=task_id, base_version_number=base_version_number)
        if deleted_task_dict is None:
            raise HTTPException(status_code=404, detail="Task not found in the specified context (live or historical version).")
        logger.info(f"Task {task_id} (from context of base_version_number: {base_version_number}) processed for deletion lineage.")
        return {"message": f"Task {deleted_task_dict.get('id', task_id)} processed for deletion.", "deleted_task_info": deleted_task_dict}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@router.get("/download_model")
async def download_model(model: str = Query("small.en")):
    """Pre-download a Whisper model so it is ready for transcription."""
    try:
        get_model(model)
        return {"status": "downloaded", "model": model}
    except Exception as e:
        # Log the exception for debugging
        logger.error(f"Error downloading model {model}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models", response_model=list[ModelInfo])
async def get_all_model_statuses():
    """
    Returns the status (including download state) of all available Whisper models.
    """
    models = []
    for name, size in WHISPER_MODEL_SIZES_MB.items():
        models.append(
            ModelInfo(
                name=name,
                size_mb=size,
                is_downloaded=is_model_downloaded(name),
            )
        )
    return models


@router.get("/model_info/{model_name}", response_model=ModelInfo)
async def get_model_info(model_name: str):
    if model_name not in WHISPER_MODEL_SIZES_MB:
        # Fallback for models not explicitly in our list (e.g. distil-large-v2)
        # For now, return a generic size or error
        # A more advanced version could try to infer or fetch this
        logger.warning(f"Size for model '{model_name}' not explicitly defined. Returning default or error.")
        # For simplicity, let's assume if it's not in our list, we can't give accurate info easily
        # Or, we could try loading it to see if it downloads, but that's too slow for an info endpoint.
        # Let's return a placeholder size and not downloaded, or an error.
        # For now, let's be strict and only return info for models we know.
        if not is_model_downloaded(model_name): # If it's not in list AND not downloaded, it's likely unknown
             raise HTTPException(status_code=404, detail=f"Size and download status for model '{model_name}' unknown.")
        # If it IS downloaded but not in our size list (e.g. a new variant), we can't give size.
        # This case is tricky. For now, we'll rely on our list.
        # A better approach might be to have Whisper itself report size after download.

    size_mb = WHISPER_MODEL_SIZES_MB.get(model_name, 0) # Default to 0 if somehow not found after check
    downloaded = is_model_downloaded(model_name)

    # If model_name is 'large', it implies the latest 'large-vX'.
    # Whisper handles this mapping internally when loading.
    # Our size list uses 'large' as a generic key for the latest 1550MB model.

    if size_mb == 0 and not downloaded:
         # This case should ideally be caught by the initial check, but as a safeguard:
         raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found or size info unavailable.")

    logger.info(f"Model info requested for {model_name}: Size {size_mb}MB, Downloaded: {downloaded}")
    return {"name": model_name, "size_mb": size_mb, "is_downloaded": downloaded}


@router.put("/tasks/{task_id}", response_model=schemas.TaskRead)
async def update_task_endpoint(task_id: int, task_data: schemas.TaskUpdate, db: Session = Depends(get_db)):
    try:
        updated_task_dict = crud.update_task(db, task_id=task_id, task_update_data=task_data)
        if updated_task_dict is None:
            raise HTTPException(status_code=404, detail="Task not found in the specified context (live or historical version).")
        return schemas.TaskRead(**updated_task_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.post("/transcribe", response_model=schemas.TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...), model_name: str = Form("small.en")):
    logger.info(f"Transcribing audio with model: {model_name}")
    model_instance = get_model(model_name)
    audio = await file.read()
    with open("temp.wav", "wb") as f:
        f.write(audio)
    result = model_instance.transcribe("temp.wav")
    os.remove("temp.wav")
    return {"text": result["text"], "model_name": model_name}

# Placeholder for your actual site URL and name
YOUR_SITE_URL = os.getenv("YOUR_SITE_URL", "http://localhost:8000")
YOUR_SITE_NAME = os.getenv("YOUR_SITE_NAME", "Task Manager App")

# OpenRouter client initialization moved to llm.py

@router.post("/process_voice_command", response_model=schemas.LLMResponse)
async def process_voice_command(request_data: schemas.VoiceCommandRequest, db: Session = Depends(get_db)):
    if not llm.is_configured():
        raise HTTPException(status_code=503, detail="LLM service is not configured. OPENROUTER_API_KEY is missing.")

    transcribed_text = request_data.text
    base_version_num_for_llm = request_data.base_version_number # Use this for context and actions
    logger.info(f"Processing voice command: '{transcribed_text}' with base_version_number: {base_version_num_for_llm}")

    current_tasks_for_llm_data: List[Dict[str, Any]]
    if base_version_num_for_llm is not None:
        base_version_orm = crud.get_task_manager_version(db, base_version_num_for_llm)
        if not base_version_orm:
            raise HTTPException(status_code=404, detail=f"Base version {base_version_num_for_llm} not found for voice command context.")
        current_tasks_for_llm_data = list(base_version_orm.snapshot_data) # Already list of dicts
    else:
        live_tasks_orm = crud.list_tasks(db) # list_tasks returns live tasks
        current_tasks_for_llm_data = [schemas.TaskRead.from_orm(t).model_dump() for t in live_tasks_orm]
    
    current_tasks_str_for_llm = "\n".join([json.dumps(task_dict) for task_dict in current_tasks_for_llm_data])
    if not current_tasks_str_for_llm:
        current_tasks_str_for_llm = "No tasks currently exist in the selected context."

    # The extensive prompt details are now managed within llm.py and prompt.py
    try:
        instruction = llm.get_instruction(transcribed_text, current_tasks_str_for_llm)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        raise HTTPException(status_code=500, detail="Error parsing LLM response.")
    except Exception as e:
        logger.error(f"Error interacting with LLM: {e}")
        raise HTTPException(status_code=500, detail=f"Error interacting with LLM: {str(e)}")

    action = instruction.action
    processed_task_data: Optional[Dict[str, Any]] = None # Store dict from CRUD
    response_message: Optional[str] = instruction.response_message

    try:
        if action == "create_task":
            if not instruction.description:
                raise HTTPException(status_code=400, detail="LLM failed to provide description for create action.")
            task_create_payload = schemas.TaskCreate(
                description=instruction.description, 
                status=instruction.status or 'pending',
                base_version_number=base_version_num_for_llm # Pass base_version_number
            )
            if task_create_payload.status not in crud.STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status '{task_create_payload.status}' provided by LLM for create.")
            
            created_task_dict = crud.create_task(db, task_create_data=task_create_payload)
            processed_task_data = created_task_dict
            response_message = f"Task {created_task_dict['id']} ('{created_task_dict['description']}') created in '{created_task_dict['status']}'."

        elif action == "update_task":
            if instruction.task_id is None:
                raise HTTPException(status_code=400, detail="LLM failed to provide task_id for update action.")
            if instruction.status and instruction.status not in crud.STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status '{instruction.status}' provided by LLM for update.")
            
            task_update_payload = schemas.TaskUpdate(
                description=instruction.description, 
                status=instruction.status,
                base_version_number=base_version_num_for_llm # Pass base_version_number
            )
            updated_task_dict = crud.update_task(db, task_id=instruction.task_id, task_update_data=task_update_payload)
            if not updated_task_dict:
                # crud.update_task returns None if task_id not in snapshot/live based on base_version_number
                raise HTTPException(status_code=404, detail=f"Task with ID {instruction.task_id} not found in the specified context for update.")
            processed_task_data = updated_task_dict
            response_message = f"Task {updated_task_dict['id']} ('{updated_task_dict['description']}') updated."

        elif action == "delete_task":
            if instruction.task_id is None:
                raise HTTPException(status_code=400, detail="LLM failed to provide task_id for delete action.")
            
            deleted_task_dict = crud.delete_task(db, task_id=instruction.task_id, base_version_number=base_version_num_for_llm)
            if not deleted_task_dict:
                raise HTTPException(status_code=404, detail=f"Task with ID {instruction.task_id} not found in the specified context for delete.")
            response_message = f"Task {deleted_task_dict['id']} ('{deleted_task_dict['description']}') deleted."
            return {"message": response_message, "deleted_task_id": deleted_task_dict['id'], "action": action}

        elif action == "list_tasks":
            response_message = f"LLM interpreted query: '{instruction.query}'. Listing tasks from the current context."
            # Return the tasks that were used as context for the LLM
            return {"message": response_message, "tasks": current_tasks_for_llm_data, "action": action}

        elif action == "no_action":
            return {"message": response_message or "Okay.", "action": action}

        elif action == "clarify_or_refuse":
            return {"message": response_message or "The command was unclear or could not be processed.", "action": action}

        else:
            logger.error(f"LLM returned an unknown action: {action}")
            raise HTTPException(status_code=500, detail=f"LLM returned an unknown action: {action}")

    except ValueError as e: # Catch ValueErrors from CRUD (e.g., base version not found)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error processing LLM instruction '{action}': {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while processing the command.")

    final_response_task: Optional[schemas.TaskRead] = None
    if processed_task_data:
        final_response_task = schemas.TaskRead(**processed_task_data)

    return schemas.LLMResponse(action=action, task=final_response_task, message=response_message).model_dump(exclude_none=True)

app.include_router(router, prefix="/api")

# Initialize the first version if no tasks and no versions exist upon startup
# This ensures that there's always a version 0 or 1 for the frontend to fetch.
@app.on_event("startup")
async def startup_event():
    db = next(get_db()) # Get a DB session
    try:
        latest_version = crud.get_latest_task_manager_version(db)
        if not latest_version:
            # Check if there are any tasks in the live table either
            live_tasks = crud.list_tasks(db)
            if not live_tasks:
                logger.info("No versions and no tasks found. Creating initial empty version 0 or 1.")
                crud.create_task_manager_version(db) # This will create version 1 with empty tasks
            else:
                # Tasks exist but no version - this state implies an issue or an older DB state.
                # Create a version for the existing tasks.
                logger.info("Tasks found but no versions. Creating initial version from existing tasks.")
                crud.create_task_manager_version(db)
    finally:
        db.close()
