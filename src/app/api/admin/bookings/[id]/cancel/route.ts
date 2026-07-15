import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireAdminSession } from "@/lib/auth";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await requireAdminSession();
  if (!session) {
    return NextResponse.json({ error: "Nicht berechtigt." }, { status: 403 });
  }

  const { id } = await params;
  const booking = await prisma.booking.findUnique({ where: { id } });
  if (!booking || booking.status !== "CONFIRMED") {
    return NextResponse.json({ error: "Nicht gefunden oder bereits storniert." }, { status: 404 });
  }

  // Admin can cancel regardless of the 24h customer cutoff (Abschnitt 3).
  await prisma.booking.update({
    where: { id },
    data: { status: "CANCELLED", cancelledAt: new Date(), cancelledBy: session.userId },
  });

  return NextResponse.json({ ok: true });
}
