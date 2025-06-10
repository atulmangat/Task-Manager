# Task Manager

This project is a simple voice-driven task manager. It uses FastAPI with SQLite to store tasks and an HTML/JavaScript front end to display them. Voice input is transcribed with OpenAI Whisper, and a custom LLM API can process commands from the transcription.

## Requirements

- Python 3.10+
- `ffmpeg` for audio processing

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the development server:

```bash
uvicorn app.main:app --reload
```

Then open `http://localhost:8000` in your browser.
