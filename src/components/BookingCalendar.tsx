"use client";

import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { MAX_ADVANCE_DAYS } from "@/lib/booking-rules";

const DAYS_IN_VIEW = 3;
const WEEKDAY_FORMAT = new Intl.DateTimeFormat("de-DE", {
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
});

type SlotStatus = "FREE" | "BOOKED" | "MINE";

interface DaySlot {
  hour: number;
  startsAt: string;
  bays: Record<string, { status: SlotStatus; bookingId?: string }>;
}

interface AvailabilityDay {
  date: string;
  slots: DaySlot[];
}

interface AvailabilityResponse {
  bays: { id: string; name: string }[];
  now: string;
  days: AvailabilityDay[];
}

interface Selection {
  bayId: string;
  bayName: string;
  startsAt: string;
  hour: number;
  date: string;
  bookingId?: string;
}

function toDateParam(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function startOfToday(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

export function BookingCalendar({ isLoggedIn }: { isLoggedIn: boolean }) {
  const today = useMemo(() => startOfToday(), []);
  const maxStart = useMemo(() => {
    const d = new Date(today);
    d.setDate(d.getDate() + Math.max(MAX_ADVANCE_DAYS - DAYS_IN_VIEW + 1, 0));
    return d;
  }, [today]);

  const [viewStart, setViewStart] = useState(today);
  const [data, setData] = useState<AvailabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async (start: Date) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/availability?start=${toDateParam(start)}&days=${DAYS_IN_VIEW}`
      );
      if (!res.ok) throw new Error("Verfügbarkeit konnte nicht geladen werden.");
      const json: AvailabilityResponse = await res.json();
      setData(json);
    } catch {
      setError("Verfügbarkeit konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    startTransition(() => {
      load(viewStart);
      setSelection(null);
      setActionError(null);
    });
  }, [viewStart, load]);

  function goPrev() {
    const d = new Date(viewStart);
    d.setDate(d.getDate() - DAYS_IN_VIEW);
    setViewStart(d < today ? today : d);
  }

  function goNext() {
    const d = new Date(viewStart);
    d.setDate(d.getDate() + DAYS_IN_VIEW);
    setViewStart(d > maxStart ? maxStart : d);
  }

  function selectSlot(
    bayId: string,
    bayName: string,
    slot: DaySlot,
    date: string
  ) {
    const status = slot.bays[bayId];
    if (!status) return;
    if (status.status === "BOOKED") return;
    setActionError(null);
    setSelection({
      bayId,
      bayName,
      startsAt: slot.startsAt,
      hour: slot.hour,
      date,
      bookingId: status.status === "MINE" ? status.bookingId : undefined,
    });
  }

  async function confirmBooking() {
    if (!selection) return;
    setSubmitting(true);
    setActionError(null);
    const res = await fetch("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bayId: selection.bayId,
        startsAt: selection.startsAt,
      }),
    });
    setSubmitting(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setActionError(body.error ?? "Buchung fehlgeschlagen.");
      return;
    }
    setSelection(null);
    load(viewStart);
  }

  async function cancelBooking() {
    if (!selection?.bookingId) return;
    setSubmitting(true);
    setActionError(null);
    const res = await fetch(`/api/bookings/${selection.bookingId}/cancel`, {
      method: "POST",
    });
    setSubmitting(false);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setActionError(body.error ?? "Stornierung fehlgeschlagen.");
      return;
    }
    setSelection(null);
    load(viewStart);
  }

  return (
    <div className="pb-24">
      <div className="mb-4 flex items-center justify-between">
        <button
          onClick={goPrev}
          disabled={viewStart <= today}
          className="rounded-md border border-black/20 px-3 py-1.5 text-sm disabled:opacity-30 dark:border-white/20"
        >
          ← Zurück
        </button>
        <p className="text-sm text-black/60 dark:text-white/60">
          {WEEKDAY_FORMAT.format(viewStart)} –{" "}
          {WEEKDAY_FORMAT.format(
            new Date(
              viewStart.getFullYear(),
              viewStart.getMonth(),
              viewStart.getDate() + DAYS_IN_VIEW - 1
            )
          )}
        </p>
        <button
          onClick={goNext}
          disabled={viewStart >= maxStart}
          className="rounded-md border border-black/20 px-3 py-1.5 text-sm disabled:opacity-30 dark:border-white/20"
        >
          Weiter →
        </button>
      </div>

      {loading && <p className="text-sm">Lädt…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {data && !loading && (
        <div className="flex flex-col gap-6">
          {data.days.map((day) => (
            <section key={day.date}>
              <h2 className="mb-2 text-sm font-semibold">
                {WEEKDAY_FORMAT.format(new Date(day.date + "T00:00:00"))}
              </h2>
              <div className="overflow-hidden rounded-lg border border-black/10 dark:border-white/10">
                <div
                  className="grid text-xs font-medium text-black/50 dark:text-white/50"
                  style={{
                    gridTemplateColumns: `3.5rem repeat(${data.bays.length}, 1fr)`,
                  }}
                >
                  <div className="px-2 py-1.5">Zeit</div>
                  {data.bays.map((bay) => (
                    <div key={bay.id} className="px-2 py-1.5 text-center">
                      {bay.name}
                    </div>
                  ))}
                </div>
                {day.slots.map((slot) => (
                  <div
                    key={slot.hour}
                    className="grid border-t border-black/5 dark:border-white/5"
                    style={{
                      gridTemplateColumns: `3.5rem repeat(${data.bays.length}, 1fr)`,
                    }}
                  >
                    <div className="flex items-center px-2 py-1 text-xs text-black/50 dark:text-white/50">
                      {String(slot.hour).padStart(2, "0")}:00
                    </div>
                    {data.bays.map((bay) => {
                      const status = slot.bays[bay.id]?.status ?? "BOOKED";
                      const isSelected =
                        selection?.bayId === bay.id &&
                        selection?.startsAt === slot.startsAt;
                      return (
                        <button
                          key={bay.id}
                          onClick={() =>
                            isLoggedIn &&
                            selectSlot(bay.id, bay.name, slot, day.date)
                          }
                          disabled={!isLoggedIn || status === "BOOKED"}
                          className={[
                            "m-0.5 rounded py-1 text-xs transition-colors",
                            status === "FREE" &&
                              "bg-emerald-100 hover:bg-emerald-200 dark:bg-emerald-900/40 dark:hover:bg-emerald-900/70",
                            status === "MINE" &&
                              "bg-sky-200 dark:bg-sky-800",
                            status === "BOOKED" &&
                              "bg-black/10 text-black/30 dark:bg-white/10 dark:text-white/30",
                            isSelected && "ring-2 ring-black dark:ring-white",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                        >
                          {status === "FREE" && "frei"}
                          {status === "MINE" && "deins"}
                          {status === "BOOKED" && "belegt"}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {!isLoggedIn && (
        <p className="mt-6 text-sm text-black/60 dark:text-white/60">
          Bitte einloggen, um eine Bay zu buchen.
        </p>
      )}

      {selection && (
        <div className="fixed inset-x-0 bottom-0 border-t border-black/10 bg-white p-4 dark:border-white/10 dark:bg-black">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm">
              {selection.bayName} · {selection.date} ·{" "}
              {String(selection.hour).padStart(2, "0")}:00 Uhr
              {selection.bookingId ? " (deine Buchung)" : ""}
            </p>
            <div className="flex items-center gap-2">
              {actionError && (
                <p className="text-sm text-red-600">{actionError}</p>
              )}
              {selection.bookingId ? (
                <button
                  onClick={cancelBooking}
                  disabled={submitting}
                  className="rounded-md border border-red-600 px-4 py-2 text-sm font-medium text-red-600 disabled:opacity-50"
                >
                  {submitting ? "…" : "Stornieren"}
                </button>
              ) : (
                <button
                  onClick={confirmBooking}
                  disabled={submitting}
                  className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
                >
                  {submitting ? "…" : "Jetzt buchen"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
