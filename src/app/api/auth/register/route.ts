import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { hashPassword, createSessionToken, setSessionCookie } from "@/lib/auth";
import { DEFAULT_TENANT_ID } from "@/lib/tenant";

const registerSchema = z.object({
  name: z.string().trim().min(1, "Name ist erforderlich."),
  address: z.string().trim().min(1, "Adresse ist erforderlich."),
  phone: z.string().trim().min(1, "Telefonnummer ist erforderlich."),
  email: z.string().trim().email("Ungültige E-Mail-Adresse."),
  password: z.string().min(8, "Passwort muss mindestens 8 Zeichen haben."),
  marketingOptIn: z.boolean().optional().default(false),
  privacyAccepted: z.literal(true, {
    error: "Die Datenschutzerklärung muss akzeptiert werden.",
  }),
});

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = registerSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Ungültige Eingabe." },
      { status: 400 }
    );
  }
  const { name, address, phone, email, password, marketingOptIn } =
    parsed.data;

  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) {
    return NextResponse.json(
      { error: "Für diese E-Mail-Adresse existiert bereits ein Konto." },
      { status: 409 }
    );
  }

  const passwordHash = await hashPassword(password);
  const user = await prisma.user.create({
    data: {
      tenantId: DEFAULT_TENANT_ID,
      name,
      address,
      phone,
      email,
      passwordHash,
      marketingOptIn,
      privacyAcceptedAt: new Date(),
    },
  });

  const token = await createSessionToken({
    userId: user.id,
    role: user.role,
    tenantId: user.tenantId,
  });
  await setSessionCookie(token);

  return NextResponse.json({ id: user.id, name: user.name });
}
