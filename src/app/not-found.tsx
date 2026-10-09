export default function NotFound() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.75rem",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: "#a16207",
        background: "#0a0a0a",
      }}
    >
      <div style={{ fontSize: "2rem", fontWeight: 700 }}>404</div>
      <div style={{ opacity: 0.7 }}>This path does not exist in the Replay Console.</div>
      <a href="/" style={{ color: "#d97706", textDecoration: "underline" }}>
        Back to the console
      </a>
    </div>
  );
}
