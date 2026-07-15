import Link from "next/link";
import { getCurrentUser } from "@/lib/auth";
import { LogoutButton } from "@/components/LogoutButton";

export async function Nav() {
  const user = await getCurrentUser();

  return (
    <header className="sticky top-0 z-10 border-b border-black/10 bg-white/90 backdrop-blur dark:border-white/10 dark:bg-black/90">
      <nav className="mx-auto flex max-w-3xl items-center justify-between gap-2 px-4 py-3 text-sm">
        <Link href="/booking" className="font-semibold">
          Majors Golfbox
        </Link>
        <div className="flex items-center gap-3">
          {user?.role === "ADMIN" && (
            <Link href="/admin" className="underline underline-offset-2">
              Admin
            </Link>
          )}
          {user ? (
            <>
              <span className="hidden sm:inline text-black/60 dark:text-white/60">
                {user.name}
              </span>
              <LogoutButton />
            </>
          ) : (
            <>
              <Link href="/login" className="underline underline-offset-2">
                Login
              </Link>
              <Link href="/register" className="underline underline-offset-2">
                Registrieren
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
