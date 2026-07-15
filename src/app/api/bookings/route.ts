import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { getSession } from "@/lib/auth";
import { slotEnd, validateBookingRequest } from "@/lib/booking-rules";

const createBookingSchema = z.object({
  bayId: z.string().min(1),
  startsAt: z.string().min(1),
});

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Bitte einloggen." }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  const parsed = createBookingSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Ungültige Eingabe." }, { status: 400 });
  }

  const startsAt = new Date(parsed.data.startsAt);
  if (Number.isNaN(startsAt.getTime())) {
    return NextResponse.json({ error: "Ungültiger Zeitpunkt." }, { status: 400 });
  }

  const [user, bay] = await Promise.all([
    prisma.user.findUnique({ where: { id: session.userId } }),
    prisma.bay.findUnique({ where: { id: parsed.data.bayId } }),
  ]);
  if (!user || !bay || bay.tenantId !== session.tenantId) {
    return NextResponse.json({ error: "Ungültige Anfrage." }, { status: 400 });
  }

  const now = new Date();
  const openBookingsCount = await prisma.booking.count({
    where: { userId: user.id, status: "CONFIRMED", startsAt: { gte: now } },
  });

  const validation = validateBookingRequest({
    startsAt,
    now,
    customerType: user.customerType,
    isInstructed: user.isInstructed,
    existingOpenBookingsCount: openBookingsCount,
  });
  if (!validation.ok) {
    return NextResponse.json({ error: validation.reason }, { status: 422 });
  }

  try {
    const booking = await prisma.booking.create({
      data: {
        bayId: bay.id,
        userId: user.id,
        startsAt,
        endsAt: slotEnd(startsAt),
        status: "CONFIRMED",
        type: "CUSTOMER",
      },
    });
    return NextResponse.json({ id: booking.id });
  } catch {
    return NextResponse.json(
      { error: "Dieser Slot ist bereits belegt." },
      { status: 409 }
    );
  }
}
