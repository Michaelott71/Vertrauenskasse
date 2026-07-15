import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { requireAdminSession } from "@/lib/auth";
import { slotEnd, isFullHourStart } from "@/lib/booking-rules";

const blockSchema = z.object({
  bayId: z.string().min(1),
  startsAt: z.string().min(1),
  paid: z.boolean().optional().default(false),
});

export async function POST(request: Request) {
  const session = await requireAdminSession();
  if (!session) {
    return NextResponse.json({ error: "Nicht berechtigt." }, { status: 403 });
  }

  const body = await request.json().catch(() => null);
  const parsed = blockSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Ungültige Eingabe." }, { status: 400 });
  }

  const startsAt = new Date(parsed.data.startsAt);
  if (Number.isNaN(startsAt.getTime()) || !isFullHourStart(startsAt)) {
    return NextResponse.json(
      { error: "Blocks starten nur zur vollen Stunde." },
      { status: 422 }
    );
  }

  const bay = await prisma.bay.findUnique({ where: { id: parsed.data.bayId } });
  if (!bay || bay.tenantId !== session.tenantId) {
    return NextResponse.json({ error: "Ungültige Bay." }, { status: 400 });
  }

  try {
    const booking = await prisma.booking.create({
      data: {
        bayId: bay.id,
        startsAt,
        endsAt: slotEnd(startsAt),
        status: "CONFIRMED",
        type: parsed.data.paid ? "ADMIN_BLOCK_PAID" : "ADMIN_BLOCK_FREE",
        paymentStatus: parsed.data.paid ? "PAID" : "NONE",
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
