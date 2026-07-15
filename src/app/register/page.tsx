"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const form = new FormData(event.currentTarget);
    const payload = {
      name: form.get("name"),
      address: form.get("address"),
      phone: form.get("phone"),
      email: form.get("email"),
      password: form.get("password"),
      marketingOptIn: form.get("marketingOptIn") === "on",
      privacyAccepted: form.get("privacyAccepted") === "on",
    };

    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    setSubmitting(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "Registrierung fehlgeschlagen.");
      return;
    }
    router.push("/booking");
    router.refresh();
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-xl font-semibold">Registrieren</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field label="Name" name="name" required />
        <Field label="Adresse" name="address" required />
        <Field label="Telefonnummer" name="phone" type="tel" required />
        <Field label="E-Mail" name="email" type="email" required />
        <Field
          label="Passwort"
          name="password"
          type="password"
          minLength={8}
          required
        />

        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" name="marketingOptIn" className="mt-1" />
          <span>
            Ich möchte den Newsletter mit Neuigkeiten und Angeboten erhalten.
          </span>
        </label>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            name="privacyAccepted"
            required
            className="mt-1"
          />
          <span>
            Ich habe die Datenschutzerklärung gelesen und akzeptiere sie.
          </span>
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {submitting ? "Wird registriert…" : "Registrieren"}
        </button>
      </form>
      <p className="mt-4 text-sm text-black/60 dark:text-white/60">
        Schon registriert?{" "}
        <Link href="/login" className="underline underline-offset-2">
          Zum Login
        </Link>
      </p>
    </div>
  );
}

function Field({
  label,
  name,
  type = "text",
  required,
  minLength,
}: {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  minLength?: number;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{label}</span>
      <input
        name={name}
        type={type}
        required={required}
        minLength={minLength}
        className="rounded-md border border-black/20 px-3 py-2 dark:border-white/20 dark:bg-transparent"
      />
    </label>
  );
}
