import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { verifyPassword, createSessionToken, setSessionCookie } from "@/lib/auth";

const loginSchema = z.object({
  email: z.string().trim().email(),
  password: z.string().min(1),
});

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = loginSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Ungültige Eingabe." }, { status: 400 });
  }

  const { email, password } = parsed.data;
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user || !(await verifyPassword(password, user.passwordHash))) {
    return NextResponse.json(
      { error: "E-Mail oder Passwort ist falsch." },
      { status: 401 }
    );
  }

  const token = await createSessionToken({
    userId: user.id,
    role: user.role,
    tenantId: user.tenantId,
  });
  await setSessionCookie(token);

  return NextResponse.json({ id: user.id, name: user.name, role: user.role });
}
