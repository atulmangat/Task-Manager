from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from . import models, schemas, crud
import requests
import os

app = FastAPI()

# create database tables
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("app/static/index.html") as f:
        return HTMLResponse(f.read())

@app.post("/tasks", response_model=schemas.TaskRead)
async def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    return crud.create_task(db, task)

@app.get("/tasks", response_model=list[schemas.TaskRead])
async def get_tasks(db: Session = Depends(get_db)):
    return crud.list_tasks(db)

@app.put("/tasks/{task_id}", response_model=schemas.TaskRead)
async def update_task(task_id: int, task: schemas.TaskUpdate, db: Session = Depends(get_db)):
    db_task = crud.update_task(db, task_id, task)
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return db_task

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        import whisper
    except ModuleNotFoundError:
        raise HTTPException(status_code=500, detail="whisper package not installed")

    model = whisper.load_model("base")
    audio = await file.read()
    with open("temp.wav", "wb") as f:
        f.write(audio)
    result = model.transcribe("temp.wav")
    os.remove("temp.wav")
    return {"text": result["text"]}

@app.post("/llm")
async def process_llm(text: str):
    url = os.getenv("LLM_API_URL")
    if not url:
        raise HTTPException(status_code=500, detail="LLM_API_URL not set")
    resp = requests.post(url, json={"text": text}, timeout=60)
    resp.raise_for_status()
    return resp.json()
