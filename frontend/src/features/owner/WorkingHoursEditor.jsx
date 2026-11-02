import { useState } from 'react'

import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { errorMessage } from '../../utils/errors.js'
import { useListWorkingHoursQuery } from '../businesses/businessesApi.js'
import { WEEKDAYS, hhmm } from './formHelpers.js'
import { useCreateWorkingHoursMutation, useDeleteWorkingHoursMutation } from './ownerApi.js'

/** Weekly shifts for one staff member, in the business's local time. */
export default function WorkingHoursEditor({ staff, timeZone }) {
  const shifts = useListWorkingHoursQuery({ staff: staff.id })
  const [createShift, creation] = useCreateWorkingHoursMutation()
  const [deleteShift, deletion] = useDeleteWorkingHoursMutation()
  const [form, setForm] = useState({ weekday: '0', start_time: '09:00', end_time: '17:00' })

  async function add(event) {
    event.preventDefault()
    try {
      await createShift({ staff: staff.id, ...form, weekday: Number(form.weekday) }).unwrap()
    } catch {
      // e.g. "Overlaps another shift on the same weekday." shown below
    }
  }

  return (
    <div className="hours">
      <h4>
        Weekly hours <span className="muted">({timeZone})</span>
      </h4>
      {shifts.isLoading ? (
        <Loading />
      ) : shifts.error ? (
        <ErrorMessage error={shifts.error} onRetry={shifts.refetch} />
      ) : shifts.data.results.length === 0 ? (
        <Empty>No hours yet: {staff.display_name} can't be booked until you add some.</Empty>
      ) : (
        <ul className="list">
          {shifts.data.results.map((shift) => (
            <li key={shift.id} className="row">
              <span>
                {WEEKDAYS[shift.weekday]} {hhmm(shift.start_time)}–{hhmm(shift.end_time)}
              </span>
              <button
                type="button"
                className="btn btn-small btn-danger"
                disabled={deletion.isLoading}
                onClick={() => deleteShift(shift.id)}
                aria-label={`Remove ${WEEKDAYS[shift.weekday]} ${hhmm(shift.start_time)} shift`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="form-row" onSubmit={add} aria-label={`Add hours for ${staff.display_name}`}>
        <label>
          Day
          <select value={form.weekday} onChange={(e) => setForm({ ...form, weekday: e.target.value })}>
            {WEEKDAYS.map((day, index) => (
              <option key={day} value={index}>
                {day}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="time" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
        </label>
        <label>
          To
          <input type="time" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
        </label>
        <div className="actions" style={{ alignItems: 'end' }}>
          <button type="submit" className="btn" disabled={creation.isLoading}>
            Add hours
          </button>
        </div>
      </form>
      {creation.error && <ErrorMessage>{errorMessage(creation.error)}</ErrorMessage>}
    </div>
  )
}
