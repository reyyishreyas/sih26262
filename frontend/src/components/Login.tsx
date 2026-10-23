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

const DEMO_PASSWORD = "DemoPassw0rd!";

type Persona = null | "college" | "officer";

export function Login({
  onSignedIn,
  notice,
}: {
  onSignedIn: (user: SessionUser) => void;
  notice?: string | null;
}) {
  const [persona, setPersona] = useState<Persona>(null);
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

        {persona === null && (
          <>
            <p className="login-sub">
              Who are you? Tap the panel that matches you.
            </p>

            {notice && <p className="message">{notice}</p>}
            {error && <p className="error">{error}</p>}

            <div className="persona-grid">
              <button
                type="button"
                className="persona-card persona-college"
                disabled={busy !== null}
                onClick={() => void pick("institution@demo.local", "college")}
              >
                <span className="persona-icon" aria-hidden>
                  <Icon name="building" size={30} />
                </span>
                <span className="persona-name">I am the College</span>
                <span className="persona-desc">
                  I send in my application and documents
                </span>
                <span className="persona-cta">
                  {busy === "college" ? "Signing in…" : "Sign in as College"}
                  {busy !== "college" && <Icon name="arrowRight" size={16} />}
                </span>
              </button>

              <button
                type="button"
                className="persona-card persona-checker"
                disabled={busy !== null}
                onClick={() => setPersona("officer")}
              >
                <span className="persona-icon" aria-hidden>
                  <Icon name="userCheck" size={30} />
                </span>
                <span className="persona-name">I am the Checker</span>
                <span className="persona-desc">
                  I review, verify and approve applications
                </span>
                <span className="persona-cta">
                  Choose my role
                  <Icon name="arrowRight" size={16} />
                </span>
              </button>
            </div>
          </>
        )}

        {persona === "officer" && (
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
                </button>
              ))}
            </div>
            <button
              type="button"
              className="link back-link"
              onClick={() => setPersona(null)}
            >
              <Icon name="arrowLeft" size={14} /> I am not a checker
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
