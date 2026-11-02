import { errorCode, errorMessage } from '../../utils/errors.js'

/**
 * Turns a booking API error into a sentence for the user.
 *
 * The backend tags each booking rule violation with a stable `code`
 * (apps/bookings/services.py). Switching on the code rather than the English
 * `detail` text means the wording here can change freely without breaking.
 */
export function bookingErrorMessage(error, { staffName } = {}) {
  switch (errorCode(error)) {
    case 'slot_unavailable':
      return 'Sorry, this slot was just taken by someone else. The free times below are up to date. Please pick another.'
    case 'outside_working_hours':
      return `That time is outside ${staffName ?? 'the staff member'}'s working hours.`
    case 'invalid_request':
      // e.g. "start must be in the future", "the hold on this booking has expired"
      return capitalise(error.data.detail)
    default:
      return errorMessage(error)
  }
}

const capitalise = (text) => (text ? text[0].toUpperCase() + text.slice(1) + '.' : '')
