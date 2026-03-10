export default function ChatPanel({
  messages,
  assistantDraft,
  draft,
  busy,
  muted,
  llmProvider,
  ttsProvider,
  sessionId,
  stageUrl,
  error,
  onDraftChange,
  onSubmit,
  onStop,
  onReset,
  onToggleMute,
  onChangeLLM,
  onChangeTTS
}) {
  return (
    <section className="chat-panel">
      <header className="panel-header">
        <div>
          <h1>AI VTuber Live</h1>
          <p className="muted">Session: {sessionId}</p>
        </div>
        <div className="row gap">
          <button onClick={onReset} disabled={busy}>
            重置 Session
          </button>
          <button onClick={onToggleMute}>{muted ? "取消靜音" : "靜音"}</button>
          <button onClick={onStop} disabled={!busy}>
            停止回覆
          </button>
        </div>
      </header>

      <div className="provider-row">
        <label>
          LLM
          <select value={llmProvider} onChange={(e) => onChangeLLM(e.target.value)}>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
          </select>
        </label>
        <label>
          TTS
          <select value={ttsProvider} onChange={(e) => onChangeTTS(e.target.value)}>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
          </select>
        </label>
      </div>

      <div className="stage-link">
        Stage View:
        <a href={stageUrl} target="_blank" rel="noreferrer">
          {stageUrl}
        </a>
      </div>

      <div className="transcript">
        {messages.map((message) => (
          <article key={message.id} className={`bubble ${message.role}`}>
            <strong>{message.role === "user" ? "你" : "VTuber"}</strong>
            <p>{message.content}</p>
          </article>
        ))}
        {assistantDraft ? (
          <article className="bubble assistant draft">
            <strong>VTuber</strong>
            <p>{assistantDraft}</p>
          </article>
        ) : null}
      </div>

      {error ? <p className="error">{error}</p> : null}

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={draft}
          placeholder="輸入你想和角色說的話..."
          onChange={(event) => onDraftChange(event.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          {busy ? "回覆中..." : "送出"}
        </button>
      </form>
    </section>
  );
}
