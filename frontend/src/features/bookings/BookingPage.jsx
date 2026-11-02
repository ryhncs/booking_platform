import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { addDays, formatDateTime, formatTime, todayIn, zoneLabel } from '../../utils/datetime.js'
import { errorCode } from '../../utils/errors.js'
import {
  useGetBusinessQuery,
  useListServicesQuery,
  useListStaffQuery,
} from '../businesses/businessesApi.js'
import { bookingErrorMessage } from './bookingErrors.js'
import { useCreateBookingMutation, useGetAvailabilityQuery } from './bookingsApi.js'

// Must match MAX_DAYS_AHEAD in apps/bookings/views.py.
const MAX_DAYS_AHEAD = 180

/**
 * Pick service -> staff -> date -> slot, then book.
 *
 * The choices live in the URL (?service=5&staff=7&date=2026-11-09) rather than
 * in component state, so the Back button, a page refresh or a shared link all
 * restore them, and the business page can link straight to a pre-filled form.
 */
export default function BookingPage() {
  const businessId = Number(useParams().businessId)
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const business = useGetBusinessQuery(businessId)
  const services = useListServicesQuery({ business: businessId })
  const staff = useListStaffQuery({ business: businessId })

  const timeZone = business.data?.timezone
  const today = timeZone ? todayIn(timeZone) : null
  const serviceId = Number(params.get('service')) || null
  const staffId = Number(params.get('staff')) || null
  const date = params.get('date') || today

  // The chosen slot is only meaningful for the current service/staff/date,
  // so it is plain component state that the change handlers reset.
  const [slot, setSlot] = useState(null)
  const [notes, setNotes] = useState('')
  const [createBooking, creation] = useCreateBookingMutation()

  const ready = Boolean(serviceId && staffId && date)
  // `skip` holds the query back until every argument is known.
  const availability = useGetAvailabilityQuery(
    { staff: staffId, service: serviceId, date },
    { skip: !ready },
  )

  if (business.isLoading || services.isLoading || staff.isLoading) {
    return <Loading label="Loading booking options…" />
  }
  const loadError = business.error ?? services.error ?? staff.error
  if (loadError) return <ErrorMessage error={loadError} onRetry={business.refetch} />

  // Only services someone offers, and only staff who offer the chosen service.
  const bookable = services.data.results.filter((s) => s.staff.length > 0)
  const service = bookable.find((s) => s.id === serviceId) ?? null
  const staffOptions = staff.data.results.filter((m) => !service || service.staff.includes(m.id))
  const servicesForStaff = staffId ? bookable.filter((s) => s.staff.includes(staffId)) : bookable
  const member = staffOptions.find((m) => m.id === staffId) ?? null

  // Update one URL parameter and forget the selected slot and any old error.
  function choose(changes) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
    setSlot(null)
    creation.reset()
  }

  function chooseService(id) {
    const chosen = bookable.find((s) => s.id === Number(id))
    // Keep the staff choice only if they offer the new service.
    const keepStaff = chosen && staffId && chosen.staff.includes(staffId)
    // If exactly one person offers it, pick them: one less click.
    const onlyStaff = chosen?.staff.length === 1 ? chosen.staff[0] : null
    choose({ service: id, staff: keepStaff ? staffId : onlyStaff })
  }

  async function book() {
    try {
      const booking = await createBooking({
        staff: staffId,
        service: serviceId,
        start: slot,
        notes,
      }).unwrap()
      // Navigation state carries the new booking to the next page for a
      // one-off success message (it isn't in the URL, so a refresh drops it).
      navigate('/bookings', { state: { justBooked: booking } })
    } catch (error) {
      // The slot list refetches on 409 (see createBooking's invalidatesTags);
      // clear the choice so the user can't resubmit a slot that's gone.
      if (errorCode(error) === 'slot_unavailable') setSlot(null)
    }
  }

  return (
    <section>
      <p>
        <Link to={`/businesses/${businessId}`}>← {business.data.name}</Link>
      </p>
      <h1>Book an appointment</h1>

      <div className="card form">
        <div className="form-row">
          <label>
            Service
            <select value={serviceId ?? ''} onChange={(e) => chooseService(e.target.value)}>
              <option value="">Choose a service…</option>
              {servicesForStaff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.duration_minutes} min)
                </option>
              ))}
            </select>
          </label>
          <label>
            With
            <select
              value={staffId ?? ''}
              onChange={(e) => choose({ staff: e.target.value })}
              disabled={!service}
            >
              <option value="">Choose who…</option>
              {staffOptions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Date
            <input
              type="date"
              value={date ?? ''}
              min={today}
              max={today ? addDays(today, MAX_DAYS_AHEAD) : undefined}
              onChange={(e) => choose({ date: e.target.value })}
            />
          </label>
        </div>
        {bookable.length === 0 && <Empty>This business has no bookable services yet.</Empty>}
      </div>

      {ready && (
        <div className="card">
          <h2>
            Free times <span className="muted">({zoneLabel(timeZone)}, {timeZone})</span>
          </h2>

          {creation.error && (
            <ErrorMessage>{bookingErrorMessage(creation.error, { staffName: member?.display_name })}</ErrorMessage>
          )}

          {availability.isLoading ? (
            <Loading label="Finding free times…" />
          ) : availability.error ? (
            <ErrorMessage error={availability.error} onRetry={availability.refetch} />
          ) : availability.data.slots.length === 0 ? (
            <Empty>No free times on this day. Try another date.</Empty>
          ) : (
            <div className="slots" role="group" aria-label="Free times" aria-busy={availability.isFetching}>
              {availability.data.slots.map(({ start }) => (
                <button
                  key={start}
                  type="button"
                  className="btn slot"
                  // aria-pressed tells assistive tech (and our CSS) which one is chosen.
                  aria-pressed={slot === start}
                  onClick={() => {
                    setSlot(start)
                    creation.reset()
                  }}
                >
                  {formatTime(start, timeZone)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {slot && (
        <div className="card form">
          <p>
            <strong>{service.name}</strong> with {member?.display_name} on{' '}
            {formatDateTime(slot, timeZone)}
          </p>
          <label>
            Notes for the business (optional)
            <textarea rows={2} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={book} disabled={creation.isLoading}>
              {creation.isLoading ? 'Booking…' : `Book ${formatTime(slot, timeZone)}`}
            </button>
          </div>
          <p className="muted">You'll have 10 minutes to confirm the booking on the next page.</p>
        </div>
      )}
    </section>
  )
}
