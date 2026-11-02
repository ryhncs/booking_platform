/** "Studio Nine & Co." -> "studio-nine-co": a URL-friendly default for the slug. */
export function slugify(text) {
  return text
    .toLowerCase()
    .normalize('NFKD') // split accented letters so "é" becomes "e" + accent...
    .replace(/[̀-ͯ]/g, '') // ...and drop the accent
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50)
}

/** The browser's own timezone, if the backend accepts it; otherwise UTC. */
export function defaultTimezone(validNames) {
  const local = Intl.DateTimeFormat().resolvedOptions().timeZone
  return validNames?.includes(local) ? local : 'UTC'
}

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/** The API sends "09:00:00"; <input type="time"> and people want "09:00". */
export const hhmm = (time) => time.slice(0, 5)
