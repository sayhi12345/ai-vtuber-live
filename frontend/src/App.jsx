import { useEffect, useMemo, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import Live2DStage from "./components/Live2DStage";
import {
  createSession,
  createUser,
  getCharacters,
  getUsers,
  resetSession,
  setSessionMute,
  stopSession,
  streamChat,
  subscribeStage,
  updateUser
} from "./lib/api";
import { useSpeechQueue } from "./lib/useSpeechQueue";

const DEFAULT_LLM_PROVIDER = import.meta.env.VITE_DEFAULT_LLM_PROVIDER || "openai";
const DEFAULT_TTS_PROVIDER = import.meta.env.VITE_DEFAULT_TTS_PROVIDER || "qwen";

const SESSION_STORAGE_KEY = "ai_vtuber_session_v2";

function loadStoredSession() {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.session_id || !parsed?.session_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

function persistSession(session) {
  if (session) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } else {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }
  // Drop the legacy key from the pre-token contract.
  window.localStorage.removeItem("ai_vtuber_session_id");
}

function createMessage(role, content) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content
  };
}

function ChatPage() {
  const [messagesByScope, setMessagesByScope] = useState({});
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
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(() => {
    const saved = window.localStorage.getItem("ai_vtuber_user_id");
    return saved ? Number(saved) : null;
  });
  const [usersLoading, setUsersLoading] = useState(true);

  const scopeKey = selectedUserId && characterId ? `${selectedUserId}:${characterId}` : null;
  const messages = scopeKey ? (messagesByScope[scopeKey] || []) : [];

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

  useEffect(() => {
    let cancelled = false;
    setUsersLoading(true);
    getUsers()
      .then((data) => {
        if (cancelled) return;
        const nextUsers = data.users || [];
        setUsers(nextUsers);
        setSelectedUserId((prev) => {
          if (prev && nextUsers.some((user) => user.id === prev)) {
            return prev;
          }
          return nextUsers[0]?.id || null;
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setUsersLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [session, setSession] = useState(() => loadStoredSession());
  const sessionId = session?.session_id || null;
  const sessionToken = session?.session_token || null;
  const abortRef = useRef(null);
  const draftRef = useRef("");
  const finalTextRef = useRef("");

  useEffect(() => {
    draftRef.current = assistantDraft;
  }, [assistantDraft]);

  useEffect(() => {
    persistSession(session);
  }, [session]);

  // Mint or re-mint a session whenever the bound user/character changes.
  // The server binds session.user_id at mint time, so we re-mint instead
  // of trying to mutate an existing binding.
  useEffect(() => {
    if (!selectedUserId || !characterId) return;
    if (
      session &&
      session.user_id === selectedUserId &&
      session.character_id === characterId
    ) {
      return;
    }
    let cancelled = false;
    createSession({ user_id: selectedUserId, character_id: characterId })
      .then((info) => {
        if (cancelled) return;
        setSession({
          session_id: info.session_id,
          session_token: info.session_token,
          user_id: info.user_id,
          character_id: info.character_id
        });
      })
      .catch((err) => {
        if (!cancelled) setError(`Session mint failed: ${err.message}`);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedUserId, characterId, session]);

  useEffect(() => {
    if (selectedUserId) {
      window.localStorage.setItem("ai_vtuber_user_id", String(selectedUserId));
    } else {
      window.localStorage.removeItem("ai_vtuber_user_id");
    }
  }, [selectedUserId]);

  const { enqueue, stop, resetStop } = useSpeechQueue({
    sessionId,
    sessionToken,
    muted,
    defaultProvider: ttsProvider,
    onSubtitle: setSubtitle,
    onExpression: setExpression,
    onSpeaking: setSpeaking,
    onMouth: setMouthOpen
  });

  const stageUrl = useMemo(() => {
    if (!sessionId || !sessionToken) return "";
    const url = new URL(`${window.location.origin}/stage`);
    url.searchParams.set("session_id", sessionId);
    url.searchParams.set("session_token", sessionToken);
    url.searchParams.set("tts_provider", ttsProvider);
    return url.toString();
  }, [sessionId, sessionToken, ttsProvider]);

  const handleStop = async () => {
    abortRef.current?.abort();
    stop();
    setBusy(false);
    if (!sessionId || !sessionToken) return;
    try {
      await stopSession(sessionId, sessionToken);
    } catch {
      // no-op
    }
  };

  const handleReset = async () => {
    await handleStop();
    if (sessionId && sessionToken) {
      try {
        await resetSession(sessionId, sessionToken);
      } catch {
        // no-op
      }
    }
    if (scopeKey) setMessagesByScope((prev) => ({ ...prev, [scopeKey]: [] }));
    setAssistantDraft("");
    setSubtitle("");
    setExpression("neutral");
    setError("");
  };

  const handleToggleMute = async () => {
    const next = !muted;
    setMuted(next);
    if (sessionId && sessionToken) {
      try {
        await setSessionMute(sessionId, sessionToken, next);
      } catch {
        // no-op
      }
    }
  };

  const handleChangeCharacter = (newCharacterId) => {
    setCharacterId(newCharacterId);
    setAssistantDraft("");
    setError("");
  };

  const handleChangeUser = (newUserId) => {
    setSelectedUserId(newUserId);
    setAssistantDraft("");
    setError("");
  };

  const handleCreateUser = async ({ name, bio }) => {
    setError("");
    const data = await createUser({ name, bio });
    const user = data.user;
    setUsers((prev) => [user, ...prev.filter((item) => item.id !== user.id)]);
    setSelectedUserId(user.id);
  };

  const handleUpdateUser = async (userId, updates) => {
    setError("");
    const data = await updateUser(userId, updates);
    const user = data.user;
    setUsers((prev) => prev.map((item) => (item.id === user.id ? user : item)));
    setSelectedUserId(user.id);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || !selectedUserId) {
      return;
    }
    if (!sessionId || !sessionToken) {
      setError("Session is not ready yet — please wait a moment and retry.");
      return;
    }

    setBusy(true);
    setError("");
    setDraft("");
    setAssistantDraft("");
    draftRef.current = "";
    finalTextRef.current = "";
    resetStop();

    const controller = new AbortController();
    abortRef.current = controller;
    const key = scopeKey;
    const addMsg = (role, content) => {
      if (!key) return;
      setMessagesByScope((prev) => ({
        ...prev,
        [key]: [...(prev[key] || []), createMessage(role, content)],
      }));
    };

    addMsg("user", text);

    try {
      await streamChat(
        {
          session_id: sessionId,
          session_token: sessionToken,
          user_id: selectedUserId,
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
        addMsg("assistant", finalText);
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
        users={users}
        selectedUserId={selectedUserId}
        usersLoading={usersLoading}
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
        onChangeCharacter={handleChangeCharacter}
        onChangeUser={handleChangeUser}
        onCreateUser={handleCreateUser}
        onUpdateUser={handleUpdateUser}
      />
    </main>
  );
}

function StagePage() {
  const search = new URLSearchParams(window.location.search);
  const stored = loadStoredSession();
  const sessionId = search.get("session_id") || stored?.session_id || "";
  const sessionToken = search.get("session_token") || stored?.session_token || "";
  const stageTtsProvider = search.get("tts_provider") || DEFAULT_TTS_PROVIDER;
  const [muted, setMuted] = useState(search.get("audio") === "1" ? false : true);
  const [subtitle, setSubtitle] = useState(
    sessionId && sessionToken ? "等待對話事件..." : "需要有效的 session — 請從主頁開啟。"
  );
  const [expression, setExpression] = useState("neutral");
  const [mouthOpen, setMouthOpen] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");
  const subtitleRef = useRef("");

  const { enqueue, stop } = useSpeechQueue({
    sessionId,
    sessionToken,
    muted,
    defaultProvider: stageTtsProvider,
    onSubtitle: null,
    onExpression: setExpression,
    onSpeaking: setSpeaking,
    onMouth: setMouthOpen
  });

  useEffect(() => {
    if (!sessionId || !sessionToken) return undefined;
    const unsubscribe = subscribeStage(sessionId, sessionToken, (eventName, data) => {
      if (eventName === "start") {
        subtitleRef.current = "";
        setSubtitle("");
        setError("");
      }
      if (eventName === "delta") {
        subtitleRef.current += data?.text || "";
        setSubtitle(subtitleRef.current);
      }
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
      if (eventName === "done") {
        const finalText = data?.text || subtitleRef.current;
        subtitleRef.current = finalText;
        setSubtitle(finalText || "等待對話事件...");
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
  }, [enqueue, sessionId, sessionToken, stageTtsProvider, stop]);

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
