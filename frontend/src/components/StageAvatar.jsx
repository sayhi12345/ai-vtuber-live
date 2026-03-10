export default function StageAvatar({
  expression,
  mouthOpen,
  subtitle,
  speaking,
  transparent = false
}) {
  return (
    <section className={`stage-shell ${transparent ? "transparent" : ""}`}>
      <div className={`stage-avatar expression-${expression}`}>
        <div className="avatar-head">
          <span className="avatar-eye left" />
          <span className="avatar-eye right" />
          <span
            className="avatar-mouth"
            style={{
              transform: `scaleY(${0.2 + mouthOpen * 1.8})`,
              opacity: speaking ? 1 : 0.7
            }}
          />
        </div>
        <div className="avatar-name">Kohana</div>
      </div>
      <div className="subtitle-box">{subtitle || "..."}</div>
    </section>
  );
}
