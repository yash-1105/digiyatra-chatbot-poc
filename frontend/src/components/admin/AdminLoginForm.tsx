"use client";

import { useRef, useState, type FormEvent } from "react";
import { AlertCircle, Eye, EyeOff, Info, Loader2, LockKeyhole, Mail } from "lucide-react";
import { loginAdmin } from "@/lib/api/auth-client";
import { cn } from "@/lib/cn";

interface FieldErrors {
  email?: string;
  password?: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!email.trim()) errors.email = "Enter your email address.";
  else if (!EMAIL_RE.test(email.trim())) errors.email = "Enter a valid email address, like name@example.com.";
  if (!password) errors.password = "Enter your password.";
  else if (password.length < 8) errors.password = "Password must be at least 8 characters.";
  return errors;
}

/** Only allow same-site relative redirects after login (no open redirects). */
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/admin") && !next.startsWith("//") ? next : "/admin/dashboard";
}

export function AdminLoginForm({ next, redirected }: { next?: string; redirected: boolean }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // Errors clear as the user types (not on blur), so the layout never shifts
  // under the pointer while the Login button is being pressed.
  const onChange = (field: "email" | "password", value: string) => {
    if (field === "email") setEmail(value);
    else setPassword(value);
    if (errors[field]) {
      const next = validate(field === "email" ? value : email, field === "password" ? value : password);
      setErrors((prev) => ({ ...prev, [field]: next[field] }));
    }
  };

  // On blur only flag a non-empty, invalid field (e.g. a malformed email).
  const onBlur = (field: "email" | "password") => {
    const value = field === "email" ? email : password;
    if (!value) return;
    const found = validate(email, password)[field];
    if (found) {
      setTouched((t) => ({ ...t, [field]: true }));
      setErrors((prev) => ({ ...prev, [field]: found }));
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const found = validate(email, password);
    setErrors(found);
    setTouched({ email: true, password: true });
    if (found.email) return emailRef.current?.focus();
    if (found.password) return passwordRef.current?.focus();

    setSubmitting(true);
    try {
      const result = await loginAdmin({ email: email.trim(), password });
      if (result.ok) {
        window.location.assign(safeNext(next));
        return;
      }
      setFormError(result.message);
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  };

  const showEmailErr = touched.email && errors.email;
  const showPwErr = touched.password && errors.password;
  const input =
    "w-full rounded border bg-page py-2.5 pl-10 pr-3 text-ink placeholder:text-ink-soft focus:border-brand disabled:opacity-60";

  return (
    <form noValidate onSubmit={onSubmit} className="space-y-5" aria-describedby={formError ? "login-error" : undefined}>
      {redirected && !formError ? (
        <div role="status" className="flex gap-2 rounded border border-brand/30 bg-brand-soft p-3 text-sm text-ink">
          <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
          Please sign in to access the administration area.
        </div>
      ) : null}

      {formError ? (
        <div id="login-error" role="alert" className="flex gap-2 rounded border border-danger/40 bg-danger-soft p-3 text-sm text-ink">
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
          <span>
            <strong className="block text-danger">Sign-in unsuccessful</strong>
            {formError}
          </span>
        </div>
      ) : null}

      <div>
        <label htmlFor="admin-email" className="mb-1.5 block text-sm font-medium text-heading">
          Email address <span className="text-danger" aria-hidden="true">*</span>
        </label>
        <div className="relative">
          <Mail aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" />
          <input
            ref={emailRef}
            id="admin-email"
            type="email"
            inputMode="email"
            autoComplete="username"
            required
            value={email}
            disabled={submitting}
            onChange={(e) => onChange("email", e.target.value)}
            onBlur={() => onBlur("email")}
            aria-invalid={Boolean(showEmailErr)}
            aria-describedby={showEmailErr ? "admin-email-error" : undefined}
            placeholder="name@organisation.in"
            className={cn(input, showEmailErr ? "border-danger" : "border-line")}
          />
        </div>
        {showEmailErr ? (
          <p id="admin-email-error" className="mt-1.5 text-sm text-danger">
            {errors.email}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="admin-password" className="mb-1.5 block text-sm font-medium text-heading">
          Password <span className="text-danger" aria-hidden="true">*</span>
        </label>
        <div className="relative">
          <LockKeyhole aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" />
          <input
            ref={passwordRef}
            id="admin-password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            disabled={submitting}
            onChange={(e) => onChange("password", e.target.value)}
            onBlur={() => onBlur("password")}
            aria-invalid={Boolean(showPwErr)}
            aria-describedby={showPwErr ? "admin-password-error" : undefined}
            className={cn(input, "pr-11", showPwErr ? "border-danger" : "border-line")}
          />
          <button
            type="button"
            onClick={() => setShowPassword((s) => !s)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded text-ink-soft hover:text-brand"
          >
            {showPassword ? <EyeOff aria-hidden="true" className="h-4 w-4" /> : <Eye aria-hidden="true" className="h-4 w-4" />}
          </button>
        </div>
        {showPwErr ? (
          <p id="admin-password-error" className="mt-1.5 text-sm text-danger">
            {errors.password}
          </p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="btn-pill flex w-full items-center justify-center gap-2 rounded-full py-3 font-medium disabled:cursor-wait disabled:opacity-80"
      >
        {submitting ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <LockKeyhole aria-hidden="true" className="h-4 w-4" />}
        {submitting ? "Signing in…" : "Login"}
      </button>
    </form>
  );
}
