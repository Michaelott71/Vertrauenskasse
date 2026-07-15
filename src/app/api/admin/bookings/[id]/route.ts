import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireAdminSession } from "@/lib/auth";

const DELETABLE_TYPES = ["ADMIN_BLOCK_FREE", "ADMIN_BLOCK_PAID"];

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await requireAdminSession();
  if (!session) {
    return NextResponse.json({ error: "Nicht berechtigt." }, { status: 403 });
  }

  const { id } = await params;
  const booking = await prisma.booking.findUnique({ where: { id } });
  if (!booking) {
    return NextResponse.json({ error: "Nicht gefunden." }, { status: 404 });
  }
  if (!DELETABLE_TYPES.includes(booking.type)) {
    return NextResponse.json(
      { error: "Nur Admin-Blocks können gelöscht werden. Kundenbuchungen bitte stornieren." },
      { status: 422 }
    );
  }

  await prisma.booking.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}
