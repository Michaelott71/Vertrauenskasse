import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { AdminDayView } from "@/components/AdminDayView";

export default async function AdminPage() {
  const session = await getSession();
  if (!session) redirect("/login");
  if (session.role !== "ADMIN") {
    return (
      <p className="text-sm text-red-600">
        Diese Seite ist nur für Admins zugänglich.
      </p>
    );
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Admin: Tagesübersicht</h1>
      <AdminDayView />
    </div>
  );
}
