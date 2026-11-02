// The API stores times in UTC, but a booking at a salon in Tehran happens at
// Tehran time no matter where the viewer is. So every time shown here is
// formatted in the *business's* timezone (an IANA name like "Asia/Tehran"),
// never the browser's. Intl.DateTimeFormat does the conversion for us.

export function formatDateTime(iso, timeZone) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(iso))
}

// 24-hour clock everywhere: appointment times read unambiguously ("14:30")
// and look the same in every locale.
export function formatTime(iso, timeZone) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(iso))
}

/** A short label for the zone, e.g. "GMT+3:30", to show next to times. */
export function zoneLabel(timeZone, at = new Date()) {
  const part = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' })
    .formatToParts(at)
    .find((p) => p.type === 'timeZoneName')
  return part?.value ?? timeZone
}

/** Today's date in `timeZone` as YYYY-MM-DD (the format <input type="date"> uses). */
export function todayIn(timeZone) {
  // The en-CA locale happens to format dates as YYYY-MM-DD.
  return new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date())
}

/** Shift a YYYY-MM-DD string by whole days. */
export function addDays(isoDate, days) {
  const date = new Date(`${isoDate}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
