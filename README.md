# Task Manager

This project is a simple voice-driven task manager. It uses FastAPI with SQLite to store tasks and an HTML/JavaScript front end to display them. Voice input is transcribed with OpenAI Whisper, and a button in the UI lets you choose and download a model. Commands are interpreted using the OpenRouter **Gemini Flash** model which creates or updates tasks based on your speech.

## Requirements

- Python 3.10+
- `ffmpeg` for audio processing

Install dependencies:

```bash
pip install -r requirements.txt
brew install ffmpeg
```

Run the development server:

```bash
uvicorn app.main:app --reload
```

Then open `http://localhost:8000` in your browser.

Set the following environment variable so the application can talk to OpenRouter:

```
export OPENROUTER_API_KEY=your_key_here
```
