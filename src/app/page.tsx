import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Majors Golfbox</h1>
      <p className="text-black/70 dark:text-white/70">
        Buche eine unserer beiden Trackman-Bays – 24/7, bis zu 14 Tage im
        Voraus.
      </p>
      <Link
        href="/booking"
        className="w-fit rounded-md bg-black px-4 py-2 text-sm font-medium text-white dark:bg-white dark:text-black"
      >
        Zur Buchung
      </Link>
    </div>
  );
}
