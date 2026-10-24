import { useState } from "react";
import { ApiError, login } from "../api";
import type { SessionUser } from "../types";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

/**
 * Two kinds of people use this system:
 *   1. The college (the "user") — submits applications and paperwork.
 *   2. The checker (the officer) — reviews, checks and decides.
 * The sign-in screen asks only that one question. Both logins are real
 * forms: nothing is signed in until the email and password are typed and
 * the server accepts them.
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

/** The two doors into the system, each with its own login form. */
const PERSONAS = [
  {
    key: "college",
    icon: "building" as IconName,
    name: "College",
    desc: "I send in my application and documents",
    hintEmail: "institution@demo.local",
  },
  {
    key: "checker",
    icon: "userCheck" as IconName,
    name: "Checker",
    desc: "I review, verify and approve applications",
    hintEmail: "scrutiny@demo.local",
  },
] as const;

type PersonaKey = (typeof PERSONAS)[number]["key"];
type Credentials = { email: string; password: string };

const EMPTY_FORMS: Record<PersonaKey, Credentials> = {
  college: { email: "", password: "" },
  checker: { email: "", password: "" },
};

export function Login({
  onSignedIn,
  notice,
}: {
  onSignedIn: (user: SessionUser) => void;
  notice?: string | null;
}) {
  // "roles" lets a checker pick which officer account they are; it fills the
  // email field of the checker form rather than signing in on its own.
  const [view, setView] = useState<"main" | "roles">("main");
  const [forms, setForms] = useState<Record<PersonaKey, Credentials>>(EMPTY_FORMS);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<PersonaKey | null>(null);

  function update(key: PersonaKey, field: keyof Credentials, value: string) {
    setForms((current) => ({
      ...current,
      [key]: { ...current[key], [field]: value },
    }));
    // The message belongs to what was typed before; typing clears it.
    setError(null);
  }

  async function signIn(key: PersonaKey) {
    const { email, password } = forms[key];
    const trimmedEmail = email.trim();

    // Empty fields never reach the server — the form has to be filled in.
    if (!trimmedEmail || !password) {
      setError("Fill in both the email and the password to sign in.");
      return;
    }

    setBusy(key);
    setError(null);
    try {
      onSignedIn(await login(trimmedEmail, password));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setError("That email and password do not match. Check them and try again.");
      } else {
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Sign-in failed. Please try again.",
        );
      }
    } finally {
      setBusy(null);
    }
  }

  function formFor(key: PersonaKey, persona: (typeof PERSONAS)[number]) {
    const { email, password } = forms[key];
    const ready = email.trim().length > 0 && password.length > 0;
    const busyHere = busy === key;

    return (
      <form
        key={key}
        className={`persona-card persona-${key}`}
        onSubmit={(event) => {
          event.preventDefault();
          void signIn(key);
        }}
      >
        <span className="persona-icon" aria-hidden>
          <Icon name={persona.icon} size={30} />
        </span>
        <span className="persona-name">I am the {persona.name}</span>
        <span className="persona-desc">{persona.desc}</span>

        <label className="login-field">
          <span className="credential-label">Email</span>
          <input
            type="email"
            name="email"
            autoComplete="username"
            placeholder={persona.hintEmail}
            value={email}
            disabled={busy !== null}
            onChange={(event) => update(key, "email", event.target.value)}
          />
        </label>

        <label className="login-field">
          <span className="credential-label">Password</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            placeholder="Your password"
            value={password}
            disabled={busy !== null}
            onChange={(event) => update(key, "password", event.target.value)}
          />
        </label>

        <button
          type="submit"
          className="persona-cta"
          disabled={busy !== null || !ready}
          title={
            ready
              ? `Sign in as ${persona.name}`
              : "Type the email and password first"
          }
        >
          {busyHere ? "Signing in…" : `Sign in as ${persona.name}`}
          {!busyHere && ready && <Icon name="arrowRight" size={16} />}
        </button>
      </form>
    );
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
              Who are you? Type your email and password, then sign in.
            </p>

            {notice && <p className="message">{notice}</p>}
            {error && <p className="error" role="alert">{error}</p>}

            <div className="persona-grid">
              {PERSONAS.map((persona) => formFor(persona.key, persona))}
            </div>

            <p className="note demo-credentials">
              Demo accounts — College:{" "}
              <code>institution@demo.local</code> · Checker:{" "}
              <code>scrutiny@demo.local</code> · password{" "}
              <code>{DEMO_PASSWORD}</code>
            </p>

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
            {error && <p className="error" role="alert">{error}</p>}
            <div className="role-grid">
              {OFFICERS.map((role) => (
                <button
                  key={role.email}
                  type="button"
                  className="role-card"
                  disabled={busy !== null}
                  onClick={() => {
                    // Fill the checker form with this role's email and send
                    // the person back to type the password themselves.
                    setForms((current) => ({
                      ...current,
                      checker: { email: role.email, password: "" },
                    }));
                    setError(null);
                    setView("main");
                  }}
                >
                  <span className="role-icon" aria-hidden>
                    <Icon name={role.icon} size={24} />
                  </span>
                  <span className="role-name">{role.name}</span>
                  <span className="role-desc">{role.desc}</span>
                  <span className="role-email">{role.email}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              className="link back-link"
              onClick={() => setView("main")}
            >
              <Icon name="arrowLeft" size={14} /> Back to the login forms
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
