import { useEffect, useMemo, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import Live2DStage from "./components/Live2DStage";
import {
  getCharacters,
  resetSession,
  setSessionMute,
  stopSession,
  streamChat,
  subscribeStage
} from "./lib/api";
import { useSpeechQueue } from "./lib/useSpeechQueue";

const DEFAULT_LLM_PROVIDER = import.meta.env.VITE_DEFAULT_LLM_PROVIDER || "openai";
const DEFAULT_TTS_PROVIDER = import.meta.env.VITE_DEFAULT_TTS_PROVIDER || "qwen";

function makeSessionId() {
  if (window.crypto?.randomUUID) {
    return `session-${window.crypto.randomUUID().slice(0, 8)}`;
  }
  return `session-${Math.random().toString(36).slice(2, 10)}`;
}

function createMessage(role, content) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content
  };
}

function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [assistantDraft, setAssistantDraft] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [expression, setExpression] = useState("neutral");
  const [mouthOpen, setMouthOpen] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [llmProvider, setLLMProvider] = useState(DEFAULT_LLM_PROVIDER);
  const [ttsProvider, setTTSProvider] = useState(DEFAULT_TTS_PROVIDER);
  const [characters, setCharacters] = useState([]);
  const [characterId, setCharacterId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getCharacters()
      .then((data) => {
        if (cancelled) return;
        setCharacters(data.characters || []);
        setCharacterId((prev) => prev || data.default_character_id || null);
      })
      .catch(() => {
        // selector will stay empty; /chat will fall back to backend default
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [sessionId] = useState(() => {
    const existing = window.localStorage.getItem("ai_vtuber_session_id");
    return existing || makeSessionId();
  });
  const abortRef = useRef(null);
  const draftRef = useRef("");
  const finalTextRef = useRef("");

  useEffect(() => {
    draftRef.current = assistantDraft;
  }, [assistantDraft]);

  useEffect(() => {
    window.localStorage.setItem("ai_vtuber_session_id", sessionId);
  }, [sessionId]);

  const { enqueue, stop, resetStop } = useSpeechQueue({
    sessionId,
    muted,
    defaultProvider: ttsProvider,
    onSubtitle: setSubtitle,
    onExpression: setExpression,
    onSpeaking: setSpeaking,
    onMouth: setMouthOpen
  });

  const stageUrl = useMemo(() => {
    const url = new URL(`${window.location.origin}/stage`);
    url.searchParams.set("session_id", sessionId);
    url.searchParams.set("tts_provider", ttsProvider);
    return url.toString();
  }, [sessionId, ttsProvider]);

  const handleStop = async () => {
    abortRef.current?.abort();
    stop();
    setBusy(false);
    try {
      await stopSession(sessionId);
    } catch {
      // no-op
    }
  };

  const handleReset = async () => {
    await handleStop();
    await resetSession(sessionId);
    setMessages([]);
    setAssistantDraft("");
    setSubtitle("");
    setExpression("neutral");
    setError("");
  };

  const handleToggleMute = async () => {
    const next = !muted;
    setMuted(next);
    await setSessionMute(sessionId, next);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) {
      return;
    }

    setBusy(true);
    setError("");
    setDraft("");
    setAssistantDraft("");
    draftRef.current = "";
    finalTextRef.current = "";
    resetStop();
    setMessages((prev) => [...prev, createMessage("user", text)]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        {
          session_id: sessionId,
          message: text,
          llm_provider: llmProvider,
          tts_provider: ttsProvider,
          character_id: characterId
        },
        (eventName, data) => {
          switch (eventName) {
            case "delta": {
              const delta = data?.text || "";
              draftRef.current += delta;
              setAssistantDraft(draftRef.current);
              break;
            }
            case "segment":
              enqueue(data);
              break;
            case "error":
              setError(data?.message || "Server error.");
              break;
            case "done":
              finalTextRef.current = data?.text || draftRef.current;
              break;
            case "stopped":
              setError("已停止目前回覆。");
              break;
            default:
              break;
          }
        },
        controller.signal
      );
    } catch (streamError) {
      if (streamError.name !== "AbortError") {
        setError(streamError.message);
      }
    } finally {
      abortRef.current = null;
      const finalText = (finalTextRef.current || draftRef.current).trim();
      if (finalText) {
        setMessages((prev) => [...prev, createMessage("assistant", finalText)]);
      }
      setAssistantDraft("");
      draftRef.current = "";
      finalTextRef.current = "";
      setBusy(false);
    }
  };

  return (
    <main className="layout">
      <Live2DStage
        expression={expression}
        mouthOpen={mouthOpen}
        subtitle={subtitle}
        speaking={speaking}
        onLoadError={(reason) => {
          setError(`Live2D 載入失敗，已切換 fallback avatar：${reason}`);
        }}
      />
      <ChatPanel
        messages={messages}
        assistantDraft={assistantDraft}
        draft={draft}
        busy={busy}
        muted={muted}
        llmProvider={llmProvider}
        ttsProvider={ttsProvider}
        characters={characters}
        characterId={characterId}
        sessionId={sessionId}
        stageUrl={stageUrl}
        error={error}
        onDraftChange={setDraft}
        onSubmit={handleSubmit}
        onStop={handleStop}
        onReset={handleReset}
        onToggleMute={handleToggleMute}
        onChangeLLM={setLLMProvider}
        onChangeTTS={setTTSProvider}
        onChangeCharacter={setCharacterId}
      />
    </main>
  );
}

function StagePage() {
  const search = new URLSearchParams(window.location.search);
  const sessionId =
    search.get("session_id") ||
    window.localStorage.getItem("ai_vtuber_session_id") ||
    makeSessionId();
  const stageTtsProvider = search.get("tts_provider") || DEFAULT_TTS_PROVIDER;
  const [muted, setMuted] = useState(search.get("audio") === "1" ? false : true);
  const [subtitle, setSubtitle] = useState("等待對話事件...");
  const [expression, setExpression] = useState("neutral");
  const [mouthOpen, setMouthOpen] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");

  const { enqueue, stop } = useSpeechQueue({
    sessionId,
    muted,
    defaultProvider: stageTtsProvider,
    onSubtitle: setSubtitle,
    onExpression: setExpression,
    onSpeaking: setSpeaking,
    onMouth: setMouthOpen
  });

  useEffect(() => {
    const unsubscribe = subscribeStage(sessionId, (eventName, data) => {
      if (eventName === "segment") {
        enqueue({
          text: data?.text || "",
          emotion: data?.emotion || "neutral",
          tts_provider: data?.tts_provider || stageTtsProvider
        });
      }
      if (eventName === "error") {
        setError(data?.message || "Stage stream error.");
      }
      if (eventName === "stopped") {
        stop();
        setSubtitle("已停止");
      }
      if (eventName === "mute" && typeof data?.muted === "boolean") {
        setMuted(data.muted);
      }
    });

    return () => {
      unsubscribe();
      stop();
    };
  }, [enqueue, sessionId, stageTtsProvider, stop]);

  return (
    <main className="stage-only">
      <Live2DStage
        expression={expression}
        mouthOpen={mouthOpen}
        subtitle={subtitle}
        speaking={speaking}
        transparent
        onLoadError={(reason) => {
          setError(`Live2D 載入失敗，已切換 fallback avatar：${reason}`);
        }}
      />
      <div className="stage-debug">
        <span>session: {sessionId}</span>
        <span>provider: {stageTtsProvider}</span>
        <span>{muted ? "audio: off" : "audio: on"}</span>
        {error ? <span className="error">{error}</span> : null}
      </div>
    </main>
  );
}

export default function App() {
  if (window.location.pathname.startsWith("/stage")) {
    return <StagePage />;
  }
  return <ChatPage />;
}
