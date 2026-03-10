# AI VTuber Live (MVP)

Character-first conversational web app:

- Text input chat with persona-driven LLM replies
- SSE streaming output + sentence segmentation + emotion tags
- Real TTS playback (OpenAI / Gemini) with subtitle sync
- Stage view (`/stage`) for OBS Browser Source use
- Safety filter, manual stop/mute, session metrics/logs

## Structure

```text
backend/
  app/
    main.py               # FastAPI + SSE endpoints
    safety.py             # Input/output filtering
    pipeline.py           # Segmentation, emotion tagging, SSE packer
    session_store.py      # SQLite messages/metrics/errors + stage event bus
    providers/            # OpenAI/Gemini LLM & TTS adapters
frontend/
  src/
    App.jsx               # Chat page + stage page
    components/           # Stage avatar + chat UI
    lib/                  # API client + audio/lip-sync queue
```

## Backend Setup

1. Install dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure env

```bash
cp .env.example .env
```

Required keys:

- `OPENAI_API_KEY` for OpenAI providers
- `GEMINI_API_KEY` for Gemini providers

Default cute voice mapping:

- OpenAI TTS: `coral`
- Gemini TTS: `Leda`

3. Run API server

```bash
python run.py
```

Server default: `http://localhost:8000`

## Frontend Setup

1. Install dependencies

```bash
cd frontend
npm install
```

2. Configure env

```bash
cp .env.example .env
```

Live2D model default path:

- `frontend/public/live2d/haru/haru_greeter_t03.model3.json`
- configurable with `VITE_LIVE2D_MODEL_PATH`
- Cubism Core runtime path configurable with `VITE_LIVE2D_CORE_SCRIPT_PATH`

3. Run app

```bash
npm run dev
```

Frontend default: `http://localhost:5173`

## Main API Endpoints

- `POST /api/chat/stream` - streaming chat output (SSE)
- `POST /api/tts` - synthesize one text segment into audio
- `GET /api/stage/stream?session_id=...` - stage events for OBS view
- `POST /api/session/stop` - manual stop current turn
- `POST /api/session/mute` - toggle mute
- `POST /api/session/reset` - reset session data
- `GET /api/session/{session_id}/metrics` - recent metrics

## Notes

- `Gemini TTS` uses model-driven audio output parsing (`inlineData`). If the selected Gemini TTS model response shape changes, update `backend/app/providers/gemini_provider.py`.
- Default stage route is muted (`/stage`). Append `?audio=1` if you want stage page audio playback.
- If Live2D fails to load, UI automatically falls back to the built-in avatar.
- TODO: emotion-to-expression mapping for Live2D motions/expressions.
