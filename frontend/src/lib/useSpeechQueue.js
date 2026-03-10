import { useCallback, useEffect, useRef } from "react";
import { synthesizeTts } from "./api";
import { createAudioPlayer } from "./audioPlayer";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function playMutedSpeechPattern(text, onSpeaking, onMouth, shouldStop) {
  const durationMs = Math.max(700, text.length * 92);
  const stepMs = 75;
  const pattern = [0.16, 0.44, 0.2, 0.58, 0.24, 0.36, 0.18, 0.5];
  let elapsedMs = 0;
  let frame = 0;

  onSpeaking?.(true);
  while (elapsedMs < durationMs && !shouldStop()) {
    const remainingMs = durationMs - elapsedMs;
    const fadeOut = remainingMs < 220 ? remainingMs / 220 : 1;
    const nextValue = pattern[frame % pattern.length] * fadeOut;
    onMouth?.(nextValue);
    await sleep(Math.min(stepMs, remainingMs));
    elapsedMs += stepMs;
    frame += 1;
  }
  onSpeaking?.(false);
  onMouth?.(0);
}

export function useSpeechQueue({
  sessionId,
  muted,
  defaultProvider,
  onSubtitle,
  onExpression,
  onSpeaking,
  onMouth
}) {
  const queueRef = useRef([]);
  const runningRef = useRef(false);
  const stopRef = useRef(false);
  const mutedRef = useRef(muted);
  const providerRef = useRef(defaultProvider);

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    providerRef.current = defaultProvider;
  }, [defaultProvider]);

  const playerRef = useRef(null);
  if (!playerRef.current) {
    playerRef.current = createAudioPlayer({
      onAmplitude: (value) => onMouth?.(value),
      onStart: () => onSpeaking?.(true),
      onEnd: () => {
        onSpeaking?.(false);
        onMouth?.(0);
      }
    });
  }

  const runQueue = useCallback(async () => {
    if (runningRef.current) {
      return;
    }
    runningRef.current = true;

    while (queueRef.current.length > 0 && !stopRef.current) {
      const segment = queueRef.current.shift();
      const text = segment?.text || "";
      if (!text.trim()) {
        continue;
      }
      const emotion = segment?.emotion || "neutral";
      onSubtitle?.(text);
      onExpression?.(emotion);

      if (mutedRef.current) {
        await playMutedSpeechPattern(
          text,
          onSpeaking,
          onMouth,
          () => stopRef.current
        );
        continue;
      }

      try {
        const blob = await synthesizeTts({
          sessionId,
          text,
          provider: segment.tts_provider || providerRef.current,
          emotion
        });
        if (blob) {
          await playerRef.current.playBlob(blob);
        }
      } catch (error) {
        console.error(error);
      }
    }

    runningRef.current = false;
  }, [onExpression, onMouth, onSpeaking, onSubtitle, sessionId]);

  const enqueue = useCallback(
    (segment) => {
      stopRef.current = false;
      queueRef.current.push(segment);
      runQueue();
    },
    [runQueue]
  );

  const stop = useCallback(() => {
    stopRef.current = true;
    queueRef.current = [];
    playerRef.current?.stop();
    onSpeaking?.(false);
    onMouth?.(0);
  }, [onMouth, onSpeaking]);

  const resetStop = useCallback(() => {
    stopRef.current = false;
  }, []);

  useEffect(() => {
    return () => {
      playerRef.current?.stop();
    };
  }, []);

  return { enqueue, stop, resetStop };
}
