import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireAdminSession } from "@/lib/auth";
import { DEFAULT_TENANT_ID } from "@/lib/tenant";

function parseDateParam(value: string | null): Date {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

export async function GET(request: Request) {
  const session = await requireAdminSession();
  if (!session) {
    return NextResponse.json({ error: "Nicht berechtigt." }, { status: 403 });
  }

  const { searchParams } = new URL(request.url);
  const date = parseDateParam(searchParams.get("date"));
  const nextDay = new Date(date);
  nextDay.setDate(nextDay.getDate() + 1);

  const [bays, bookings] = await Promise.all([
    prisma.bay.findMany({
      where: { tenantId: DEFAULT_TENANT_ID },
      orderBy: { name: "asc" },
    }),
    prisma.booking.findMany({
      where: {
        bay: { tenantId: DEFAULT_TENANT_ID },
        startsAt: { gte: date, lt: nextDay },
        status: { in: ["CONFIRMED", "NO_SHOW", "COMPLETED"] },
      },
      include: { user: { select: { name: true, customerType: true } } },
    }),
  ]);

  const bookingsBySlot = new Map<string, (typeof bookings)[number]>();
  for (const booking of bookings) {
    bookingsBySlot.set(`${booking.bayId}|${booking.startsAt.toISOString()}`, booking);
  }

  const slots = [];
  for (let hour = 0; hour < 24; hour++) {
    const slotStart = new Date(date);
    slotStart.setHours(hour, 0, 0, 0);
    const bayEntries: Record<string, unknown> = {};
    for (const bay of bays) {
      const booking = bookingsBySlot.get(`${bay.id}|${slotStart.toISOString()}`);
      bayEntries[bay.id] = booking
        ? {
            status: "OCCUPIED",
            bookingId: booking.id,
            type: booking.type,
            customerName: booking.user?.name ?? null,
            customerType: booking.user?.customerType ?? null,
          }
        : { status: "FREE" };
    }
    slots.push({ hour, startsAt: slotStart.toISOString(), bays: bayEntries });
  }

  return NextResponse.json({
    bays: bays.map((b) => ({ id: b.id, name: b.name })),
    date: date.toISOString().slice(0, 10),
    slots,
  });
}
