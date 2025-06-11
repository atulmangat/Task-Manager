from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from . import models, schemas, crud
try:
    import whisper  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    whisper = None
import requests
import json
import os

app = FastAPI()

# Cache for loaded whisper models so they are downloaded only once
if whisper is not None:
    MODEL_CACHE: dict[str, whisper.Whisper] = {}
else:  # pragma: no cover - whisper not installed
    MODEL_CACHE: dict[str, object] = {}

# create database tables
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

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

@app.post("/tasks", response_model=schemas.TaskRead)
async def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    return crud.create_task(db, task)

@app.get("/tasks", response_model=list[schemas.TaskRead])
async def get_tasks(db: Session = Depends(get_db)):
    return crud.list_tasks(db)


@app.get("/download_model")
async def download_model(model: str = Query("base")):
    """Pre-download a Whisper model so it is ready for transcription."""
    get_model(model)
    return {"status": "downloaded"}

@app.put("/tasks/{task_id}", response_model=schemas.TaskRead)
async def update_task(task_id: int, task: schemas.TaskUpdate, db: Session = Depends(get_db)):
    db_task = crud.update_task(db, task_id, task)
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return db_task

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...), model: str = Query("base")
):
    model_instance = get_model(model)
    audio = await file.read()
    with open("temp.wav", "wb") as f:
        f.write(audio)
    result = model_instance.transcribe("temp.wav")
    os.remove("temp.wav")
    return {"text": result["text"]}

@app.post("/llm")
async def process_llm(text: str, db: Session = Depends(get_db)):
    """Use the OpenRouter Gemini Flash model to interpret the user's intent."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "google/gemini-flash-1.5",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a task manager assistant. "
                    "Extract the user's intent from the text and respond with a JSON "
                    "object. Supported actions are 'create' and 'update'. For 'create', "
                    "provide 'description' and optional 'status'. For 'update', provide "
                    "'id' and 'status'. Respond only with JSON."
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]
    try:
        command = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid response from LLM")

    action = command.get("action")
    if action == "create":
        description = command.get("description")
        status = command.get("status", "pending")
        if not description:
            raise HTTPException(status_code=400, detail="Description required")
        task = crud.create_task(db, schemas.TaskCreate(description=description, status=status))
        return schemas.TaskRead.from_orm(task)
    elif action == "update":
        task_id = command.get("id")
        status = command.get("status")
        if task_id is None or status is None:
            raise HTTPException(status_code=400, detail="id and status required")
        task = crud.update_task(db, task_id, schemas.TaskUpdate(status=status))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return schemas.TaskRead.from_orm(task)
    return {"message": "No action"}
