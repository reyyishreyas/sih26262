import { useState } from "react";
import { ApiError, login } from "../api";
import type { SessionUser } from "../types";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

/**
 * Two kinds of people use this system:
 *   1. The college (the "user") — submits applications and paperwork.
 *   2. The checker (the officer) — reviews, checks and decides.
 * The sign-in screen asks only that one question.
 */

const OFFICERS = [
  {
    email: "scrutiny@demo.local",
    icon: "search" as IconName,
    name: "Review Officer",
    desc: "I check the documents",
  },
  {
    email: "regional@demo.local",
    icon: "mapPin" as IconName,
    name: "Regional Officer",
    desc: "I oversee my region",
  },
  {
    email: "evc@demo.local",
    icon: "users" as IconName,
    name: "Committee Member",
    desc: "I approve after the visit",
  },
  {
    email: "supervisor@demo.local",
    icon: "chart" as IconName,
    name: "Supervisor",
    desc: "I watch progress and alerts",
  },
  {
    email: "admin@demo.local",
    icon: "settings" as IconName,
    name: "Administrator",
    desc: "I manage the whole system",
  },
] as const;

export const DEMO_PASSWORD = "DemoPassw0rd!";

/** The two doors into the system, with the demo login shown on each card. */
const PERSONAS = [
  {
    key: "college",
    email: "institution@demo.local",
    icon: "building" as IconName,
    name: "College",
    desc: "I send in my application and documents",
  },
  {
    key: "checker",
    email: "scrutiny@demo.local",
    icon: "userCheck" as IconName,
    name: "Checker",
    desc: "I review, verify and approve applications",
  },
] as const;

export function Login({
  onSignedIn,
  notice,
}: {
  onSignedIn: (user: SessionUser) => void;
  notice?: string | null;
}) {
  // "roles" opens the secondary list of checker roles; the main screen itself
  // is always the two cards below, credentials and all.
  const [view, setView] = useState<"main" | "roles">("main");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function pick(email: string, who: string) {
    setBusy(who);
    setError(null);
    try {
      onSignedIn(await login(email, DEMO_PASSWORD));
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Sign-in failed. Please try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="login">
      <div className="login-card">
        <div className="login-mark" aria-hidden>
          <Icon name="cap" size={30} />
        </div>
        <h1>AICTE Approvals — Made Simple</h1>

        {view === "main" && (
          <>
            <p className="login-sub">
              Who are you? Tap your panel — the demo login is on it, so one tap
              signs you in.
            </p>

            {notice && <p className="message">{notice}</p>}
            {error && <p className="error">{error}</p>}

            <div className="persona-grid">
              {PERSONAS.map((persona) => (
                <button
                  key={persona.key}
                  type="button"
                  className={`persona-card persona-${persona.key}`}
                  disabled={busy !== null}
                  onClick={() => void pick(persona.email, persona.key)}
                >
                  <span className="persona-icon" aria-hidden>
                    <Icon name={persona.icon} size={30} />
                  </span>
                  <span className="persona-name">I am the {persona.name}</span>
                  <span className="persona-desc">{persona.desc}</span>
                  <span className="persona-credentials" title="Demo login — one tap signs you in">
                    <span className="credential-row">
                      <span className="credential-label">Email</span>
                      <span className="credential-value">{persona.email}</span>
                    </span>
                    <span className="credential-row">
                      <span className="credential-label">Password</span>
                      <span className="credential-value">{DEMO_PASSWORD}</span>
                    </span>
                  </span>
                  <span className="persona-cta">
                    {busy === persona.key
                      ? "Signing in…"
                      : `Sign in as ${persona.name}`}
                    {busy !== persona.key && <Icon name="arrowRight" size={16} />}
                  </span>
                </button>
              ))}
            </div>

            <button
              type="button"
              className="link back-link"
              onClick={() => setView("roles")}
            >
              Sign in as a different checker role
              <Icon name="arrowRight" size={14} />
            </button>
          </>
        )}

        {view === "roles" && (
          <>
            <p className="login-sub">Which checker are you?</p>
            {error && <p className="error">{error}</p>}
            <div className="role-grid">
              {OFFICERS.map((role) => (
                <button
                  key={role.email}
                  type="button"
                  className="role-card"
                  disabled={busy !== null}
                  onClick={() => void pick(role.email, role.email)}
                >
                  <span className="role-icon" aria-hidden>
                    {busy === role.email ? (
                      <span className="spinner" />
                    ) : (
                      <Icon name={role.icon} size={24} />
                    )}
                  </span>
                  <span className="role-name">{role.name}</span>
                  <span className="role-desc">
                    {busy === role.email ? "Signing in…" : role.desc}
                  </span>
                  <span className="role-email">{role.email}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              className="link back-link"
              onClick={() => setView("main")}
            >
              <Icon name="arrowLeft" size={14} /> Back to the two panels
            </button>
          </>
        )}

        <p className="note">
          Demo system. Every person, college and document here is made up for
          testing.
        </p>
      </div>
    </main>
  );
}
