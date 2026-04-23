import { useEffect, useMemo, useState } from "react";

export default function ChatPanel({
  messages,
  assistantDraft,
  draft,
  busy,
  muted,
  llmProvider,
  ttsProvider,
  characters,
  characterId,
  users,
  selectedUserId,
  usersLoading,
  sessionId,
  stageUrl,
  error,
  onDraftChange,
  onSubmit,
  onStop,
  onReset,
  onToggleMute,
  onChangeLLM,
  onChangeTTS,
  onChangeCharacter,
  onChangeUser,
  onCreateUser,
  onUpdateUser
}) {
  const currentCharacter = characters?.find((c) => c.id === characterId) || null;
  const selectedUser = useMemo(
    () => users?.find((user) => user.id === selectedUserId) || null,
    [selectedUserId, users]
  );
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
          角色
          <select
            value={characterId || ""}
            onChange={(e) => onChangeCharacter(e.target.value || null)}
            disabled={!characters?.length}
          >
            {characters?.length ? (
              characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))
            ) : (
              <option value="">載入中...</option>
            )}
          </select>
        </label>
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
            <option value="qwen">Qwen Local</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
          </select>
        </label>
      </div>
      {currentCharacter?.short_description ? (
        <p className="muted character-desc">{currentCharacter.short_description}</p>
      ) : null}

      <UserProfilePanel
        users={users}
        selectedUser={selectedUser}
        selectedUserId={selectedUserId}
        loading={usersLoading}
        busy={busy}
        onChangeUser={onChangeUser}
        onCreateUser={onCreateUser}
        onUpdateUser={onUpdateUser}
      />

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
          placeholder={selectedUser ? "輸入你想和角色說的話..." : "請先建立或選擇使用者"}
          onChange={(event) => onDraftChange(event.target.value)}
          disabled={busy || !selectedUser}
        />
        <button type="submit" disabled={busy || !draft.trim() || !selectedUser}>
          {busy ? "回覆中..." : "送出"}
        </button>
      </form>
    </section>
  );
}

function UserProfilePanel({
  users,
  selectedUser,
  selectedUserId,
  loading,
  busy,
  onChangeUser,
  onCreateUser,
  onUpdateUser
}) {
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [saving, setSaving] = useState(false);
  const [profileError, setProfileError] = useState("");

  useEffect(() => { setName(""); }, [selectedUser?.id]);
  useEffect(() => { setBio(selectedUser?.bio || ""); }, [selectedUser?.id, selectedUser?.bio]);

  const withSaving = async (action) => {
    setSaving(true);
    setProfileError("");
    try { await action(); }
    catch (err) { setProfileError(err.message); }
    finally { setSaving(false); }
  };

  const handleCreate = (event) => {
    event.preventDefault();
    const cleanName = name.trim();
    if (!cleanName) { setProfileError("請輸入名稱。"); return; }
    withSaving(async () => {
      await onCreateUser({ name: cleanName, bio });
      setName("");
      setBio("");
    });
  };

  const handleQuickAdd = () => {
    const cleanName = name.trim();
    if (!cleanName) { setProfileError("請輸入名稱。"); return; }
    withSaving(async () => {
      await onCreateUser({ name: cleanName, bio: "" });
      setName("");
    });
  };

  const handleUpdate = (event) => {
    event.preventDefault();
    if (!selectedUser) return;
    withSaving(() => onUpdateUser(selectedUser.id, { name: selectedUser.name, bio }));
  };

  if (loading) {
    return <div className="profile-panel muted">載入使用者...</div>;
  }

  if (!users?.length) {
    return (
      <form className="profile-panel profile-create" onSubmit={handleCreate}>
        <div className="profile-title">建立使用者</div>
        <input
          value={name}
          placeholder="你的名字"
          onChange={(event) => setName(event.target.value)}
          disabled={saving || busy}
        />
        <textarea
          value={bio}
          placeholder="簡短介紹，角色會把它當作你的基本資料"
          onChange={(event) => setBio(event.target.value)}
          disabled={saving || busy}
        />
        {profileError ? <p className="error">{profileError}</p> : null}
        <button type="submit" disabled={saving || busy || !name.trim()}>
          {saving ? "儲存中..." : "建立並選擇"}
        </button>
      </form>
    );
  }

  return (
    <form className="profile-panel" onSubmit={handleUpdate}>
      <div className="profile-controls">
        <label>
          使用者
          <select
            value={selectedUserId || ""}
            onChange={(event) => onChangeUser(Number(event.target.value) || null)}
            disabled={busy || saving}
          >
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={saving || busy || !selectedUser}>
          {saving ? "儲存中..." : "更新 Bio"}
        </button>
      </div>
      <textarea
        value={bio}
        placeholder="補充你的偏好、背景或想讓角色知道的事"
        onChange={(event) => setBio(event.target.value)}
        disabled={saving || busy || !selectedUser}
      />
      <details className="profile-add">
        <summary>新增另一位使用者</summary>
        <div className="profile-add-grid">
          <input
            value={name}
            placeholder="新使用者名稱"
            onChange={(event) => setName(event.target.value)}
            disabled={saving || busy}
          />
          <button
            type="button"
            disabled={saving || busy || !name.trim()}
            onClick={handleQuickAdd}
          >
            建立
          </button>
        </div>
      </details>
      {profileError ? <p className="error">{profileError}</p> : null}
    </form>
  );
}
