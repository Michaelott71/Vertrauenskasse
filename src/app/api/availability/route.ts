import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getSession } from "@/lib/auth";
import { DEFAULT_TENANT_ID } from "@/lib/tenant";

const OCCUPIED_STATUSES = ["CONFIRMED", "NO_SHOW", "COMPLETED"] as const;
const MAX_DAYS_PER_REQUEST = 7;

function parseDateParam(value: string | null): Date {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const start = parseDateParam(searchParams.get("start"));
  const days = Math.min(
    Math.max(Number(searchParams.get("days") ?? 3) || 3, 1),
    MAX_DAYS_PER_REQUEST
  );

  const rangeEnd = new Date(start);
  rangeEnd.setDate(rangeEnd.getDate() + days);

  const session = await getSession();

  const [bays, bookings] = await Promise.all([
    prisma.bay.findMany({
      where: { tenantId: DEFAULT_TENANT_ID },
      orderBy: { name: "asc" },
    }),
    prisma.booking.findMany({
      where: {
        bay: { tenantId: DEFAULT_TENANT_ID },
        startsAt: { gte: start, lt: rangeEnd },
        status: { in: [...OCCUPIED_STATUSES] },
      },
      include: { user: { select: { id: true, name: true } } },
    }),
  ]);

  const bookingsBySlot = new Map<string, (typeof bookings)[number]>();
  for (const booking of bookings) {
    bookingsBySlot.set(`${booking.bayId}|${booking.startsAt.toISOString()}`, booking);
  }

  const dayList = [];
  for (let i = 0; i < days; i++) {
    const date = new Date(start);
    date.setDate(date.getDate() + i);
    const slots = [];
    for (let hour = 0; hour < 24; hour++) {
      const slotStart = new Date(date);
      slotStart.setHours(hour, 0, 0, 0);
      const bayStatuses: Record<
        string,
        { status: "FREE" | "BOOKED" | "MINE"; bookingId?: string }
      > = {};
      for (const bay of bays) {
        const booking = bookingsBySlot.get(
          `${bay.id}|${slotStart.toISOString()}`
        );
        if (!booking) {
          bayStatuses[bay.id] = { status: "FREE" };
        } else if (session && booking.userId === session.userId) {
          bayStatuses[bay.id] = { status: "MINE", bookingId: booking.id };
        } else {
          bayStatuses[bay.id] = { status: "BOOKED" };
        }
      }
      slots.push({ hour, startsAt: slotStart.toISOString(), bays: bayStatuses });
    }
    dayList.push({ date: date.toISOString().slice(0, 10), slots });
  }

  return NextResponse.json({
    bays: bays.map((b) => ({ id: b.id, name: b.name })),
    now: new Date().toISOString(),
    days: dayList,
  });
}
