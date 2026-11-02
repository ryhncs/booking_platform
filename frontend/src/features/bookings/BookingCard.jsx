import { useState } from 'react'

import { ErrorMessage } from '../../components/Status.jsx'
import { formatDateTime, formatTime, zoneLabel } from '../../utils/datetime.js'
import { bookingErrorMessage } from './bookingErrors.js'
import { useCancelBookingMutation, useConfirmBookingMutation } from './bookingsApi.js'
import { cancelledByLabel } from './cancelledBy.js'

/**
 * One booking with the actions that make sense for its status.
 *
 * Used by both "My bookings" (viewer = customer) and "Incoming bookings"
 * (viewer = owner); the API lets either party confirm or cancel.
 *
 * Each card has its own mutation hooks, so confirming one booking shows a
 * busy state on that card only. After a mutation, RTK Query refetches the
 * list (tag invalidation), and this card re-renders with the new status.
 */
export default function BookingCard({ booking, viewer, currentUserId }) {
  const [confirm, confirmState] = useConfirmBookingMutation()
  const [cancel, cancelState] = useCancelBookingMutation()
  const [cancelling, setCancelling] = useState(false)
  const [reason, setReason] = useState('')
  // Render functions must be pure, and Date.now() returns something new on
  // every call, so read the clock once, when the card mounts. If a hold
  // expires while the page stays open, the server still enforces it: the
  // confirm request fails with a clear "hold has expired" message.
  const [mountedAt] = useState(() => Date.now())

  const tz = booking.business_timezone
  const isActive = booking.status === 'pending' || booking.status === 'confirmed'
  const holdExpired =
    booking.status === 'pending' && booking.expires_at && new Date(booking.expires_at) <= mountedAt
  const busy = confirmState.isLoading || cancelState.isLoading
  const error = confirmState.error ?? cancelState.error

  async function submitCancel(event) {
    event.preventDefault()
    try {
      await cancel({ id: booking.id, reason: reason.trim() }).unwrap()
      setCancelling(false)
    } catch {
      // shown via cancelState.error
    }
  }

  return (
    <li className="card booking">
      <div className="row">
        <div>
          <strong>{booking.service_name}</strong> with {booking.staff_name}
          <div className="muted">
            {viewer === 'owner' ? `Customer: ${booking.customer_name}` : booking.business_name}
          </div>
        </div>
        <span className={`badge badge-${booking.status}`}>{booking.status}</span>
      </div>

      <p>
        {formatDateTime(booking.start, tz)}–{formatTime(booking.end, tz)}{' '}
        <span className="muted">
          ({zoneLabel(tz, new Date(booking.start))}, {tz})
        </span>
      </p>

      {booking.notes && <p className="muted">Notes: {booking.notes}</p>}

      {booking.status === 'pending' &&
        (holdExpired ? (
          <p className="alert alert-warning">This hold has expired and will be released shortly.</p>
        ) : (
          booking.expires_at && (
            <p className="alert alert-warning">
              Not confirmed yet: the slot is held until {formatTime(booking.expires_at, tz)}.
            </p>
          )
        ))}

      {booking.status === 'cancelled' && (
        <p className="muted">
          Cancelled by {cancelledByLabel(booking, currentUserId)}
          {booking.cancellation_reason ? `: “${booking.cancellation_reason}”` : '.'}
        </p>
      )}

      {error && <ErrorMessage>{bookingErrorMessage(error)}</ErrorMessage>}

      {isActive && !cancelling && (
        <div className="actions">
          {booking.status === 'pending' && !holdExpired && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => confirm(booking.id)}
            >
              {confirmState.isLoading ? 'Confirming…' : 'Confirm'}
            </button>
          )}
          <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setCancelling(true)}>
            Cancel…
          </button>
        </div>
      )}

      {isActive && cancelling && (
        <form className="form" onSubmit={submitCancel}>
          <label>
            Reason (optional, shared with the {viewer === 'owner' ? 'customer' : 'business'})
            <textarea rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" className="btn btn-danger" disabled={busy}>
              {cancelState.isLoading ? 'Cancelling…' : 'Cancel booking'}
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => setCancelling(false)}>
              Keep booking
            </button>
          </div>
        </form>
      )}
    </li>
  )
}
