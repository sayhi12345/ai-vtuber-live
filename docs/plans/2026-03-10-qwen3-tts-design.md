# Qwen3-TTS Local Provider Design

## Goal

Replace the default remote OpenAI TTS path with an in-process local `Qwen3-TTS` provider while keeping the existing chat and frontend playback flow unchanged.

## Chosen Approach

- Add a new backend `qwen` TTS provider that lazy-loads `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`.
- Keep OpenAI and Gemini available for LLM and fallback TTS selection.
- Switch the app default TTS provider to `qwen`.
- Preserve the existing `/api/tts` contract so the frontend queue and lip-sync path do not need architectural changes.

## Data Flow

1. Frontend sends `provider: "qwen"` to `POST /api/tts`.
2. Backend registry resolves the local `QwenProvider`.
3. The provider lazy-loads the model on first use and runs generation in a worker thread.
4. Generated waveform is encoded to WAV bytes and returned to the existing audio player.

## Error Handling

- Missing `qwen-tts` runtime dependencies return a `ProviderError` with a clear install hint.
- Model load failures return a provider-specific error with the configured model id.
- Empty waveform output is treated as a TTS failure.

## Testing

- Run existing backend tests to ensure non-TTS paths still pass.
- Validate that the frontend still offers OpenAI/Gemini and now defaults to `Qwen Local`.
- Manual runtime verification still requires installing `qwen-tts` and downloading the model weights.
