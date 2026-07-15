"use client";

import { startTransition, useCallback, useEffect, useState } from "react";

type BookingType =
  | "CUSTOMER"
  | "ADMIN_BLOCK_FREE"
  | "ADMIN_BLOCK_PAID"
  | "TRAINER_SLOT";

interface BaySlotInfo {
  status: "FREE" | "OCCUPIED";
  bookingId?: string;
  type?: BookingType;
  customerName?: string | null;
  customerType?: string | null;
}

interface Slot {
  hour: number;
  startsAt: string;
  bays: Record<string, BaySlotInfo>;
}

interface AdminDayResponse {
  bays: { id: string; name: string }[];
  date: string;
  slots: Slot[];
}

function toDateParam(date: Date): string {
  return date.toISOString().slice(0, 10);
}

const TYPE_LABEL: Record<BookingType, string> = {
  CUSTOMER: "Kunde",
  ADMIN_BLOCK_FREE: "Block (frei)",
  ADMIN_BLOCK_PAID: "Block (bezahlt)",
  TRAINER_SLOT: "Trainer",
};

export function AdminDayView() {
  const [date, setDate] = useState(() => toDateParam(new Date()));
  const [data, setData] = useState<AdminDayResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busySlot, setBusySlot] = useState<string | null>(null);

  const load = useCallback(async (d: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/bookings?date=${d}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      setError("Daten konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    startTransition(() => {
      load(date);
    });
  }, [date, load]);

  async function block(bayId: string, startsAt: string, paid: boolean) {
    setBusySlot(`${bayId}|${startsAt}`);
    setError(null);
    const res = await fetch("/api/admin/block", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bayId, startsAt, paid }),
    });
    setBusySlot(null);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.error ?? "Blocken fehlgeschlagen.");
      return;
    }
    load(date);
  }

  async function removeBlock(bookingId: string) {
    setBusySlot(bookingId);
    setError(null);
    const res = await fetch(`/api/admin/bookings/${bookingId}`, {
      method: "DELETE",
    });
    setBusySlot(null);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.error ?? "Löschen fehlgeschlagen.");
      return;
    }
    load(date);
  }

  async function cancelBooking(bookingId: string) {
    setBusySlot(bookingId);
    setError(null);
    const res = await fetch(`/api/admin/bookings/${bookingId}/cancel`, {
      method: "POST",
    });
    setBusySlot(null);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.error ?? "Stornieren fehlgeschlagen.");
      return;
    }
    load(date);
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded-md border border-black/20 px-3 py-1.5 text-sm dark:border-white/20 dark:bg-transparent"
        />
      </div>

      {loading && <p className="text-sm">Lädt…</p>}
      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      {data && !loading && (
        <div className="overflow-hidden rounded-lg border border-black/10 dark:border-white/10">
          <div
            className="grid text-xs font-medium text-black/50 dark:text-white/50"
            style={{ gridTemplateColumns: `3.5rem repeat(${data.bays.length}, 1fr)` }}
          >
            <div className="px-2 py-1.5">Zeit</div>
            {data.bays.map((bay) => (
              <div key={bay.id} className="px-2 py-1.5 text-center">
                {bay.name}
              </div>
            ))}
          </div>
          {data.slots.map((slot) => (
            <div
              key={slot.hour}
              className="grid border-t border-black/5 dark:border-white/5"
              style={{ gridTemplateColumns: `3.5rem repeat(${data.bays.length}, 1fr)` }}
            >
              <div className="flex items-center px-2 py-1 text-xs text-black/50 dark:text-white/50">
                {String(slot.hour).padStart(2, "0")}:00
              </div>
              {data.bays.map((bay) => {
                const info = slot.bays[bay.id];
                const key = `${bay.id}|${slot.startsAt}`;
                const isBusy = busySlot === key || busySlot === info?.bookingId;
                if (!info || info.status === "FREE") {
                  return (
                    <div key={bay.id} className="m-0.5 flex gap-1">
                      <button
                        disabled={isBusy}
                        onClick={() => block(bay.id, slot.startsAt, false)}
                        className="flex-1 rounded bg-emerald-100 py-1 text-[11px] disabled:opacity-50 dark:bg-emerald-900/40"
                      >
                        Block frei
                      </button>
                      <button
                        disabled={isBusy}
                        onClick={() => block(bay.id, slot.startsAt, true)}
                        className="flex-1 rounded bg-amber-100 py-1 text-[11px] disabled:opacity-50 dark:bg-amber-900/40"
                      >
                        Block bezahlt
                      </button>
                    </div>
                  );
                }
                const type = info.type ?? "CUSTOMER";
                return (
                  <div
                    key={bay.id}
                    className="m-0.5 flex items-center justify-between rounded bg-black/5 px-1.5 py-1 text-[11px] dark:bg-white/10"
                  >
                    <span className="truncate">
                      {info.customerName ?? TYPE_LABEL[type]}
                    </span>
                    {type === "CUSTOMER" ? (
                      <button
                        disabled={isBusy}
                        onClick={() => cancelBooking(info.bookingId!)}
                        className="ml-1 shrink-0 text-red-600 disabled:opacity-50"
                      >
                        Stornieren
                      </button>
                    ) : (
                      <button
                        disabled={isBusy}
                        onClick={() => removeBlock(info.bookingId!)}
                        className="ml-1 shrink-0 text-red-600 disabled:opacity-50"
                      >
                        Löschen
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
