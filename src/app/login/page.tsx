"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const form = new FormData(event.currentTarget);
    const payload = {
      email: form.get("email"),
      password: form.get("password"),
    };

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    setSubmitting(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "Login fehlgeschlagen.");
      return;
    }
    router.push("/booking");
    router.refresh();
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-xl font-semibold">Login</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span>E-Mail</span>
          <input
            name="email"
            type="email"
            required
            className="rounded-md border border-black/20 px-3 py-2 dark:border-white/20 dark:bg-transparent"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span>Passwort</span>
          <input
            name="password"
            type="password"
            required
            className="rounded-md border border-black/20 px-3 py-2 dark:border-white/20 dark:bg-transparent"
          />
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {submitting ? "Wird eingeloggt…" : "Login"}
        </button>
      </form>
      <p className="mt-4 text-sm text-black/60 dark:text-white/60">
        Noch kein Konto?{" "}
        <Link href="/register" className="underline underline-offset-2">
          Jetzt registrieren
        </Link>
      </p>
    </div>
  );
}
