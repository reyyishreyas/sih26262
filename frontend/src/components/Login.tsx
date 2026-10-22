import { useState } from "react";
import { ApiError, login } from "../api";
import type { SessionUser } from "../types";

const DEMO_ACCOUNTS = [
  ["institution@demo.local", "Institution representative"],
  ["scrutiny@demo.local", "Scrutiny officer"],
  ["regional@demo.local", "Regional officer"],
  ["evc@demo.local", "EVC member"],
  ["supervisor@demo.local", "Supervisory officer"],
  ["admin@demo.local", "Administrator"],
] as const;

export function Login({
  onSignedIn,
  notice,
}: {
  onSignedIn: (user: SessionUser) => void;
  notice?: string | null;
}) {
  const [email, setEmail] = useState("scrutiny@demo.local");
  const [password, setPassword] = useState("DemoPassw0rd!");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await login(email, password));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <div className="login-card">
        <p className="eyebrow">SIH26262 · prototype</p>
        <h1>AICTE Approval &amp; Compliance</h1>
        <p className="muted">
          Synthetic data only. Mock OCR and mock notification delivery. Sign in with a
          seeded demo account to see the role-scoped view the server actually enforces.
        </p>
        {notice && <p className="message">{notice}</p>}
        <form onSubmit={submit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              autoComplete="username"
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <details>
          <summary>Demo accounts (password <code>DemoPassw0rd!</code>)</summary>
          <ul className="demo-accounts">
            {DEMO_ACCOUNTS.map(([address, label]) => (
              <li key={address}>
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    setEmail(address);
                    setPassword("DemoPassw0rd!");
                  }}
                >
                  {address}
                </button>{" "}
                <span className="muted">{label}</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </main>
  );
}
