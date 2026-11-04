import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'

import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import { api, server } from '../../test/server.js'
import WorkingHoursEditor from './WorkingHoursEditor.jsx'

const SARA = { id: 7, display_name: 'Sara', is_active: true }
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const shift = (id, weekday, start, end) => ({
  id,
  staff: SARA.id,
  weekday,
  start_time: `${start}:00`,
  end_time: `${end}:00`,
})

/** A small stateful backend: bulk creates and deletes change what GET returns. */
function backend(initial = [], { bulk } = {}) {
  const db = { shifts: [...initial], bulkBodies: [], deleted: [] }
  server.use(
    http.get(api('/working-hours/'), () =>
      HttpResponse.json({ count: db.shifts.length, next: null, previous: null, results: db.shifts }),
    ),
    http.post(api('/working-hours/bulk/'), async ({ request }) => {
      const body = await request.json()
      db.bulkBodies.push(body)
      if (bulk) return bulk(body)
      const created = body.weekdays.map((day, i) => shift(100 + db.shifts.length + i, day, body.start_time, body.end_time))
      db.shifts.push(...created)
      return HttpResponse.json(created, { status: 201 })
    }),
    http.delete(api('/working-hours/:id/'), ({ params }) => {
      db.deleted.push(Number(params.id))
      db.shifts = db.shifts.filter((s) => s.id !== Number(params.id))
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return db
}

const render = () =>
  renderWithProviders(<WorkingHoursEditor staff={SARA} timeZone="Asia/Tehran" />, { preloadedState: loggedIn })

/** The table row for one weekday, e.g. row('Monday'). */
const row = (day) => screen.getByRole('rowheader', { name: day }).closest('tr')
const checkbox = (day) => screen.getByRole('checkbox', { name: day })
const checkedDays = () => DAYS.filter((day) => checkbox(day).checked)

describe('WorkingHoursEditor', () => {
  test('shows existing hours grouped by weekday, in time order, with days off', async () => {
    backend([shift(1, 0, '13:00', '17:00'), shift(2, 0, '09:00', '12:00'), shift(3, 2, '10:00', '18:00')])
    render()

    await screen.findByRole('table', { name: 'Weekly hours for Sara' })
    await waitFor(() => expect(row('Monday')).toHaveTextContent('09:00–12:00'))
    expect(row('Monday').textContent.indexOf('09:00')).toBeLessThan(row('Monday').textContent.indexOf('13:00'))
    expect(row('Wednesday')).toHaveTextContent('10:00–18:00')
    for (const day of ['Tuesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']) {
      expect(row(day)).toHaveTextContent('Day off')
    }
  })

  test('quick buttons select All week, Sat–Wed, or nothing', async () => {
    backend()
    const { user } = render()
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Add hours' })).toBeDisabled() // no day chosen

    await user.click(screen.getByRole('button', { name: 'All week' }))
    expect(checkedDays()).toEqual(DAYS)

    await user.click(screen.getByRole('button', { name: 'Sat–Wed' }))
    expect(checkedDays()).toEqual(['Monday', 'Tuesday', 'Wednesday', 'Saturday', 'Sunday'])
    expect(screen.getByRole('button', { name: 'Add hours' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(checkedDays()).toEqual([])
    expect(screen.getByRole('button', { name: 'Add hours' })).toBeDisabled()
  })

  test('one "Add hours" click creates the shift on every chosen day', async () => {
    const db = backend()
    const { user } = render()
    await screen.findByRole('table')

    await user.click(checkbox('Thursday'))
    await user.click(checkbox('Tuesday'))
    // fireEvent.change sets a time input in one step (typing digit by digit
    // passes through invalid intermediate values in jsdom).
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '10:00' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '14:00' } })
    await user.click(screen.getByRole('button', { name: 'Add hours' }))

    // The table refetched (tag invalidation) and shows the new hours.
    await waitFor(() => expect(row('Tuesday')).toHaveTextContent('10:00–14:00'))
    expect(row('Thursday')).toHaveTextContent('10:00–14:00')
    expect(row('Wednesday')).toHaveTextContent('Day off')
    // One request, days sorted, exactly the shape the API expects.
    expect(db.bulkBodies).toEqual([{ staff: 7, weekdays: [1, 3], start_time: '10:00', end_time: '14:00' }])
    // The day selection resets for the next entry.
    expect(checkedDays()).toEqual([])
  })

  test('an overlap rejects the whole request and the message names the days', async () => {
    const db = backend([shift(1, 0, '09:00', '17:00')], {
      bulk: () =>
        HttpResponse.json(
          { weekdays: ['Overlaps existing hours on Monday. Nothing was added.'] },
          { status: 400 },
        ),
    })
    const { user } = render()
    await screen.findByRole('table')

    await user.click(screen.getByRole('button', { name: 'Sat–Wed' }))
    await user.click(screen.getByRole('button', { name: 'Add hours' }))

    expect(await screen.findByText('Overlaps existing hours on Monday. Nothing was added.')).toBeInTheDocument()
    expect(row('Saturday')).toHaveTextContent('Day off') // nothing was added anywhere
    expect(db.bulkBodies).toHaveLength(1)
    // Changing the selection clears the stale error.
    await user.click(checkbox('Monday'))
    expect(screen.queryByText(/Overlaps existing hours/)).not.toBeInTheDocument()
  })

  test('an end time before the start shows the API field error', async () => {
    backend([], {
      bulk: () => HttpResponse.json({ end_time: ['Must be after start_time.'] }, { status: 400 }),
    })
    const { user } = render()
    await screen.findByRole('table')

    await user.click(checkbox('Friday'))
    await user.click(screen.getByRole('button', { name: 'Add hours' }))

    expect(await screen.findByText('Must be after start_time.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^To/)).toHaveAttribute('aria-invalid', 'true')
  })

  test('removing a shift deletes it and the day becomes a day off', async () => {
    const db = backend([shift(1, 4, '09:00', '13:00')])
    const { user } = render()

    await user.click(await screen.findByRole('button', { name: 'Remove Friday 09:00–13:00' }))

    await waitFor(() => expect(row('Friday')).toHaveTextContent('Day off'))
    expect(db.deleted).toEqual([1])
    expect(within(row('Friday')).queryByRole('button')).not.toBeInTheDocument()
  })
})
