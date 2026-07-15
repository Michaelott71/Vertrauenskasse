import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getSession } from "@/lib/auth";
import { isCancellableByCustomer } from "@/lib/booking-rules";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Bitte einloggen." }, { status: 401 });
  }

  const { id } = await params;
  const booking = await prisma.booking.findUnique({ where: { id } });
  if (!booking || booking.userId !== session.userId) {
    return NextResponse.json({ error: "Buchung nicht gefunden." }, { status: 404 });
  }
  if (booking.status !== "CONFIRMED") {
    return NextResponse.json(
      { error: "Diese Buchung ist nicht mehr aktiv." },
      { status: 409 }
    );
  }
  if (!isCancellableByCustomer(booking.startsAt, new Date())) {
    return NextResponse.json(
      {
        error:
          "Eine Stornierung ist nur bis 24 Stunden vorher selbst möglich. Bitte kontaktiere den Support.",
      },
      { status: 422 }
    );
  }

  await prisma.booking.update({
    where: { id },
    data: { status: "CANCELLED", cancelledAt: new Date(), cancelledBy: session.userId },
  });

  return NextResponse.json({ ok: true });
}
