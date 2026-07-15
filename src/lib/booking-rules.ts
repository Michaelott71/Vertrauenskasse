import type { CustomerType } from "@/generated/prisma/client";

export const SLOT_DURATION_MINUTES = 55;
export const MAX_ADVANCE_DAYS = 14;
export const NEW_CUSTOMER_MIN_LEAD_HOURS = 24;
export const STANDARD_MAX_OPEN_HOURS = 10;
export const CANCELLATION_CUTOFF_HOURS = 24;

export function slotEnd(startsAt: Date): Date {
  return new Date(startsAt.getTime() + SLOT_DURATION_MINUTES * 60_000);
}

export function isFullHourStart(startsAt: Date): boolean {
  return (
    startsAt.getMinutes() === 0 &&
    startsAt.getSeconds() === 0 &&
    startsAt.getMilliseconds() === 0
  );
}

function dateOnly(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

// "heute+14 buchbar, heute+15 nicht" - compared by calendar day, not by 24h duration.
export function isWithinBookingWindow(startsAt: Date, now: Date): boolean {
  const dayDiff =
    (dateOnly(startsAt).getTime() - dateOnly(now).getTime()) /
    (24 * 60 * 60 * 1000);
  return dayDiff >= 0 && dayDiff <= MAX_ADVANCE_DAYS;
}

export function isNewCustomerLeadTimeOk(
  customerType: CustomerType,
  isInstructed: boolean,
  startsAt: Date,
  now: Date
): boolean {
  if (customerType !== "NEW" || isInstructed) return true;
  const leadHours = (startsAt.getTime() - now.getTime()) / (60 * 60 * 1000);
  return leadHours >= NEW_CUSTOMER_MIN_LEAD_HOURS;
}

export function isWithinStandardOpenHoursLimit(
  existingOpenBookingsCount: number
): boolean {
  const openHours =
    (existingOpenBookingsCount * SLOT_DURATION_MINUTES) / 60;
  return openHours < STANDARD_MAX_OPEN_HOURS;
}

export function isCancellableByCustomer(startsAt: Date, now: Date): boolean {
  const hoursUntilStart = (startsAt.getTime() - now.getTime()) / (60 * 60 * 1000);
  return hoursUntilStart >= CANCELLATION_CUTOFF_HOURS;
}

export interface BookingValidationInput {
  startsAt: Date;
  now: Date;
  customerType: CustomerType;
  isInstructed: boolean;
  existingOpenBookingsCount: number;
}

export interface BookingValidationResult {
  ok: boolean;
  reason?: string;
}

export function validateBookingRequest(
  input: BookingValidationInput
): BookingValidationResult {
  if (!isFullHourStart(input.startsAt)) {
    return { ok: false, reason: "Buchungen starten nur zur vollen Stunde." };
  }
  if (!isWithinBookingWindow(input.startsAt, input.now)) {
    return {
      ok: false,
      reason: `Buchungen sind maximal ${MAX_ADVANCE_DAYS} Tage im Voraus möglich.`,
    };
  }
  if (
    !isNewCustomerLeadTimeOk(
      input.customerType,
      input.isInstructed,
      input.startsAt,
      input.now
    )
  ) {
    return {
      ok: false,
      reason:
        "Als neu registrierter Kunde ist eine Buchung erst ab 1 Tag Vorlauf möglich.",
    };
  }
  if (
    input.customerType !== "MEMBER" &&
    !isWithinStandardOpenHoursLimit(input.existingOpenBookingsCount)
  ) {
    return {
      ok: false,
      reason: `Maximal ${STANDARD_MAX_OPEN_HOURS} Stunden gleichzeitig vorausgebucht möglich.`,
    };
  }
  return { ok: true };
}
