# TTS Cute Voice And Lip-Sync Design

Date: 2026-03-09
Status: approved

## Goal

1. When switching between OpenAI and Gemini TTS, the app should automatically use a cute female-leaning default voice for that provider.
2. When the VTuber is speaking, the mouth should visibly animate in sync with playback on both the main page and the OBS stage page.

## Decisions

### Provider-specific voice defaults

- OpenAI default voice: `coral`
- Gemini default voice: `Leda`
- Manual `voice` overrides still win over defaults.

This keeps the current backend contract unchanged. The provider adapter already resolves `voice or provider_default`, so the implementation only needs updated defaults in backend config and env examples.

### Lip-sync approach

- Keep the existing frontend audio amplitude analysis pipeline.
- Move Live2D mouth parameter writes to the model's `beforeModelUpdate` lifecycle so they are applied after motion and physics and are not overwritten in the same frame.
- Drive all available LipSync parameters from the model settings, falling back to `ParamMouthOpenY`.
- Add smoothing and a speaking floor so mouth motion looks intentional instead of jittery.
- For muted playback, simulate rhythmic mouth movement instead of holding a fixed mouth-open value. This preserves speaking presence on the default muted stage page.

## Implementation outline

### Backend

- Update OpenAI TTS default voice in config and `.env.example` to `coral`.
- Update Gemini TTS default voice in config and `.env.example` to `Leda`.

### Frontend

- In `useSpeechQueue`, replace the fixed muted mouth pose with a timed pulse animation that can be cancelled by stop/reset.
- In `Live2DStage`, register a `beforeModelUpdate` listener on the internal model and write the smoothed mouth value to the model's lip-sync parameters there.
- Keep fallback avatar behavior unchanged except that it receives the improved mouth values.

## Validation

- Backend tests still pass.
- Frontend production build succeeds.
- With audio enabled, the mouth opens and closes with playback.
- On `/stage` with default muted playback, the mouth still animates while subtitles are being spoken.
