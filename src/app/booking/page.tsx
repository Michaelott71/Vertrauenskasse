import { getSession } from "@/lib/auth";
import { BookingCalendar } from "@/components/BookingCalendar";

export default async function BookingPage() {
  const session = await getSession();

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Bay-Verfügbarkeit</h1>
      <BookingCalendar isLoggedIn={Boolean(session)} />
    </div>
  );
}
