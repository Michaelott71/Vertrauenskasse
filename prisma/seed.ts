import bcrypt from "bcryptjs";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "../src/generated/prisma/client";

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

async function main() {
  const tenant = await prisma.tenant.upsert({
    where: { id: "golfbox" },
    update: {},
    create: { id: "golfbox", name: "Majors Golfbox" },
  });

  for (const name of ["Bay 1", "Bay 2"]) {
    await prisma.bay.upsert({
      where: { tenantId_name: { tenantId: tenant.id, name } },
      update: {},
      create: { tenantId: tenant.id, name },
    });
  }

  const adminEmail = process.env.ADMIN_EMAIL;
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (adminEmail && adminPassword) {
    await prisma.user.upsert({
      where: { email: adminEmail },
      update: {},
      create: {
        tenantId: tenant.id,
        email: adminEmail,
        passwordHash: await bcrypt.hash(adminPassword, 12),
        name: "Admin",
        address: "-",
        phone: "-",
        role: "ADMIN",
        customerType: "MEMBER",
        isInstructed: true,
        privacyAcceptedAt: new Date(),
      },
    });
    console.log(`Admin-Benutzer angelegt: ${adminEmail}`);
  } else {
    console.log(
      "Kein ADMIN_EMAIL/ADMIN_PASSWORD gesetzt - Admin-Benutzer wird nicht angelegt."
    );
  }

  console.log("Seed complete.");
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
