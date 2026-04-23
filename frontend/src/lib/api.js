const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

function buildApiUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (API_BASE_URL.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    return `${API_BASE_URL}${normalizedPath.slice("/api".length)}`;
  }
  return `${API_BASE_URL}${normalizedPath}`;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(buildApiUrl(path), options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status} ${message}`);
  }
  return response.json();
}

function parseEventBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (!dataLines.length) {
    return null;
  }
  const joined = dataLines.join("\n");
  return { event, data: JSON.parse(joined) };
}

export async function streamChat(payload, onEvent, signal) {
  const response = await fetch(buildApiUrl("/api/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal
  });

  if (!response.ok || !response.body) {
    const message = await response.text();
    throw new Error(`Stream request failed: ${response.status} ${message}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    while (true) {
      const separatorMatch = buffer.match(/\r?\n\r?\n/);
      if (!separatorMatch || separatorMatch.index === undefined) {
        break;
      }
      const idx = separatorMatch.index;
      const block = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + separatorMatch[0].length);
      if (!block) {
        continue;
      }
      const parsed = parseEventBlock(block);
      if (parsed) {
        onEvent(parsed.event, parsed.data);
      }
    }
  }
}

export async function synthesizeTts({
  sessionId,
  text,
  provider,
  voice,
  emotion
}) {
  const response = await fetch(buildApiUrl("/api/tts"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      text,
      provider,
      voice,
      emotion
    })
  });

  if (response.status === 204) {
    return null;
  }
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`TTS failed: ${response.status} ${message}`);
  }
  return response.blob();
}

export function subscribeStage(sessionId, onEvent) {
  const url = buildApiUrl(`/api/stage/stream?session_id=${encodeURIComponent(sessionId)}`);
  const source = new EventSource(url);

  const events = ["ready", "start", "segment", "done", "error", "stopped", "mute"];
  for (const event of events) {
    source.addEventListener(event, (raw) => {
      try {
        onEvent(event, JSON.parse(raw.data));
      } catch {
        onEvent(event, {});
      }
    });
  }

  source.onerror = () => {
    onEvent("error", { message: "Stage event stream disconnected." });
  };

  return () => source.close();
}

export async function stopSession(sessionId) {
  await fetch(buildApiUrl("/api/session/stop"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  });
}

export async function setSessionMute(sessionId, muted) {
  await fetch(buildApiUrl("/api/session/mute"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, muted })
  });
}

export async function resetSession(sessionId) {
  await fetch(buildApiUrl("/api/session/reset"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  });
}

export const getCharacters = () => apiFetch("/api/characters");

export const getUsers = () => apiFetch("/api/users");

export const createUser = ({ name, bio }) =>
  apiFetch("/api/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, bio })
  });

export const updateUser = (userId, { name, bio }) =>
  apiFetch(`/api/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, bio })
  });

export const getSessionMetrics = (sessionId) =>
  apiFetch(`/api/session/${encodeURIComponent(sessionId)}/metrics`);
