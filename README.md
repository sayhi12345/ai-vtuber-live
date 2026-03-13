# AI VTuber Live (MVP)

Character-first conversational web app:

- Text input chat with persona-driven LLM replies
- Selective agent routing: skill-like requests can switch into a LangChain Deep Agents path
- SSE streaming output + sentence segmentation + emotion tags
- Real TTS playback (local Qwen / OpenAI / Gemini) with subtitle sync
- Stage view (`/stage`) for OBS Browser Source use
- Safety filter, manual stop/mute, session metrics/logs

## Structure

```text
backend/
  app/
    main.py               # FastAPI + SSE endpoints
    agents/              # Selective router + deep agent runtime
    safety.py             # Input/output filtering
    pipeline.py           # Segmentation, emotion tagging, SSE packer
    session_store.py      # SQLite messages/metrics/errors + stage event bus
    providers/            # OpenAI/Gemini LLM + Qwen local TTS adapters
  skills/                # Deep Agent skill directories (tarot, ...)
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

Agent skills:

- `deepagents` is included in `backend/requirements.txt` for Python 3.11+
- skill requests are routed selectively; normal chat still uses the standard provider flow
- current built-in agent skill: `backend/skills/tarot`
- the current local environment in this repo is Python 3.10, so agent-skill execution will require upgrading the backend runtime to Python 3.11+

Local Qwen TTS defaults:

- `DEFAULT_TTS_PROVIDER=qwen`
- `QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- `QWEN_TTS_DEVICE=auto` picks `cuda:0` when available, otherwise `cpu`
- `QWEN_TTS_ATTN_IMPLEMENTATION=sdpa` avoids requiring FlashAttention by default

The first local Qwen TTS request will download model weights from Hugging Face if they are not already cached.
Practical latency requires a CUDA-capable GPU; CPU mode is supported as a fallback but will be much slower.

Default cute voice mapping:

- OpenAI TTS: `coral`
- Gemini TTS: `Leda`
- Qwen Local TTS: `Vivian`

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
- `Qwen Local TTS` runs in-process inside the backend and lazy-loads on the first synthesis request.
- Default stage route is muted (`/stage`). Append `?audio=1` if you want stage page audio playback.
- If Live2D fails to load, UI automatically falls back to the built-in avatar.
- TODO: emotion-to-expression mapping for Live2D motions/expressions.
