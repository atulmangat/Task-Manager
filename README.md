# Task Manager

A simple voice-driven task manager with:
- **FastAPI** backend (Python, SQLite, async)
- **React/Vite** frontend (TypeScript)
- Voice input via **OpenAI Whisper**
- LLM command processing via **OpenRouter Gemini Flash**

---

## Requirements
- Python 3.11+
- Node.js 18+
- `ffmpeg` (for audio processing)

---

## Backend Setup (FastAPI)

1. **Install Python dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
2. **Install ffmpeg:**
   ```sh
   brew install ffmpeg
   ```
3. **Set environment variables:**
   - Copy `.env.example` to `.env` and set your values, or:
   ```sh
   export OPENROUTER_API_KEY=your_key_here
   ```
4. **Run the backend:**
   ```sh
   uvicorn app.main:app --reload
   ```
   - Visit [http://localhost:8000](http://localhost:8000)

---

## Frontend Setup (React/Vite)

1. **Install dependencies:**
   ```sh
   cd frontend
   npm install
   ```
2. **Run the frontend:**
   ```sh
   npm run dev
   ```
   - Default: [http://localhost:5173](http://localhost:5173)

---

## Building a Standalone Binary (macOS)

You can bundle the FastAPI backend as a standalone binary using PyInstaller:

1. **Install PyInstaller:**
   ```sh
   pip install pyinstaller
   ```
2. **Build the binary:**
   ```sh
   pyinstaller --onefile --name task-manager app/main.py
   ```
   - The binary will be in the `dist` folder as `task-manager`.

---

## Git Usage
- The repository excludes `node_modules`, virtualenvs, build artifacts, lock files, `.env`, and database files by default (`.gitignore`).
- To commit changes:
  ```sh
  git add .
  git commit -m "Your message"
  git push
  ```

---

## Notes
- Requires OpenRouter API key for LLM features.
- For production, run Uvicorn without `--reload` and consider using a process manager (e.g., systemd, supervisor).
- For static/frontend production, build with `npm run build` in `frontend/` and serve with a production web server.

---

## License
MIT
