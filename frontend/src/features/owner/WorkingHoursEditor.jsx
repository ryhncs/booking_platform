import { useState } from 'react'

import { ErrorMessage, Loading } from '../../components/Status.jsx'
import { errorMessage, fieldErrors } from '../../utils/errors.js'
import { useListWorkingHoursQuery } from '../businesses/businessesApi.js'
import { WEEKDAYS, hhmm } from './formHelpers.js'
import { useBulkCreateWorkingHoursMutation, useDeleteWorkingHoursMutation } from './ownerApi.js'

// Weekday numbers match the API: 0 = Monday ... 6 = Sunday.
const ALL_WEEK = [0, 1, 2, 3, 4, 5, 6]
// A Saturday-to-Wednesday week (common in Iran and elsewhere): Sat, Sun, Mon, Tue, Wed.
const SAT_TO_WED = [5, 6, 0, 1, 2]

/**
 * Weekly shifts for one staff member, in the business's local time.
 *
 * Pick any set of days, one From/To, and "Add hours" creates that shift on
 * every chosen day in a single request. The server does it all-or-nothing:
 * if one day would overlap, none are added and the error names the days.
 */
export default function WorkingHoursEditor({ staff, timeZone }) {
  const shifts = useListWorkingHoursQuery({ staff: staff.id })
  const [bulkCreate, creation] = useBulkCreateWorkingHoursMutation()
  const [deleteShift, deletion] = useDeleteWorkingHoursMutation()

  const [days, setDays] = useState([])
  const [start, setStart] = useState('09:00')
  const [end, setEnd] = useState('17:00')
  const fields = fieldErrors(creation.error)

  // Changing the selection makes the previous error irrelevant, so clear it.
  function selectDays(next) {
    setDays(next)
    creation.reset()
  }

  function toggleDay(day) {
    selectDays(days.includes(day) ? days.filter((d) => d !== day) : [...days, day])
  }

  async function add(event) {
    event.preventDefault()
    try {
      await bulkCreate({
        staff: staff.id,
        weekdays: [...days].sort((a, b) => a - b),
        start_time: start,
        end_time: end,
      }).unwrap()
      // Done: untick the days (keep the times, they're often reused).
      setDays([])
    } catch {
      // shown below the form
    }
  }

  // Group the flat list of shifts by weekday for the table: { 0: [...], 3: [...] }.
  const byDay = {}
  for (const shift of shifts.data?.results ?? []) {
    byDay[shift.weekday] ??= [] // start an empty list the first time we see this day
    byDay[shift.weekday].push(shift)
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
      ) : (
        <table className="week-table" aria-label={`Weekly hours for ${staff.display_name}`}>
          <tbody>
            {WEEKDAYS.map((dayName, day) => {
              const dayShifts = [...(byDay[day] ?? [])].sort((a, b) => a.start_time.localeCompare(b.start_time))
              return (
                <tr key={dayName}>
                  <th scope="row">{dayName}</th>
                  <td>
                    {dayShifts.length === 0 ? (
                      <span className="muted">Day off</span>
                    ) : (
                      dayShifts.map((shift) => (
                        <span key={shift.id} className="shift">
                          {hhmm(shift.start_time)}–{hhmm(shift.end_time)}
                          <button
                            type="button"
                            className="btn btn-small btn-danger"
                            disabled={deletion.isLoading}
                            onClick={() => deleteShift(shift.id)}
                            aria-label={`Remove ${dayName} ${hhmm(shift.start_time)}–${hhmm(shift.end_time)}`}
                          >
                            ×
                          </button>
                        </span>
                      ))
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {deletion.error && <ErrorMessage error={deletion.error} />}

      <form className="form" onSubmit={add} aria-label={`Add hours for ${staff.display_name}`}>
        <fieldset>
          <legend>Days</legend>
          <div className="day-checks">
            {WEEKDAYS.map((dayName, day) => (
              <label key={dayName}>
                <input type="checkbox" checked={days.includes(day)} onChange={() => toggleDay(day)} />
                {dayName}
              </label>
            ))}
          </div>
          <div className="actions" style={{ marginTop: 8 }}>
            {/* type="button" so these don't submit the form. */}
            <button type="button" className="btn btn-small" onClick={() => selectDays(ALL_WEEK)}>
              All week
            </button>
            <button type="button" className="btn btn-small" onClick={() => selectDays(SAT_TO_WED)}>
              Sat–Wed
            </button>
            <button type="button" className="btn btn-small" onClick={() => selectDays([])}>
              Clear
            </button>
          </div>
          {fields.weekdays && <span className="field-error">{fields.weekdays}</span>}
        </fieldset>

        <div className="form-row">
          <label>
            From
            <input type="time" required value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            To
            <input
              type="time"
              required
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              aria-invalid={Boolean(fields.end_time)}
            />
            {fields.end_time && <span className="field-error">{fields.end_time}</span>}
          </label>
        </div>

        {/* Errors that aren't tied to one input (network, permissions, ...). */}
        {creation.error && !fields.weekdays && !fields.end_time && (
          <ErrorMessage>{errorMessage(creation.error)}</ErrorMessage>
        )}

        <div className="actions">
          <button type="submit" className="btn btn-primary" disabled={days.length === 0 || creation.isLoading}>
            {creation.isLoading ? 'Adding…' : 'Add hours'}
          </button>
        </div>
      </form>
    </div>
  )
}
