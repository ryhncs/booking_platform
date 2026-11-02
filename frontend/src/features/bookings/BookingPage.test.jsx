import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, test } from 'vitest'

import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import { api, server } from '../../test/server.js'
import BookingPage from './BookingPage.jsx'

const page = (results) => ({ count: results.length, next: null, previous: null, results })
const DATE = '2030-01-07'
const slot = (hhmm) => ({
  start: `${DATE}T${hhmm}:00+03:30`,
  end: `${DATE}T${hhmm.replace(/^(\d+)/, (h) => String(Number(h) + 1).padStart(2, '0'))}:00+03:30`,
})

// Where a successful booking lands; shows the navigation state it received.
function MyBookingsStub() {
  const { state } = useLocation()
  return <p>My bookings page (new booking #{state?.justBooked?.id})</p>
}

const routes = (
  <Routes>
    <Route path="/businesses/:businessId/book" element={<BookingPage />} />
    <Route path="/bookings" element={<MyBookingsStub />} />
  </Routes>
)

let calls
function backend({ createBooking, availability } = {}) {
  calls = { availability: 0, created: [] }
  server.use(
    http.get(api('/businesses/1/'), () =>
      HttpResponse.json({ id: 1, name: 'Salon', slug: 'salon', timezone: 'Asia/Tehran' }),
    ),
    http.get(api('/services/'), () =>
      HttpResponse.json(
        page([
          { id: 5, business: 1, name: 'Haircut', duration_minutes: 60, price: '1', staff: [7], is_active: true },
          { id: 6, business: 1, name: 'Colour', duration_minutes: 90, price: '1', staff: [7, 8], is_active: true },
        ]),
      ),
    ),
    http.get(api('/staff/'), () =>
      HttpResponse.json(
        page([
          { id: 7, business: 1, display_name: 'Sara', is_active: true },
          { id: 8, business: 1, display_name: 'Nia', is_active: true },
        ]),
      ),
    ),
    http.get(api('/availability/'), ({ request }) => {
      calls.availability += 1
      const body = availability
        ? availability(calls.availability, new URL(request.url).searchParams)
        : [slot('10:00'), slot('11:00')]
      return HttpResponse.json({ staff: 7, service: 5, date: DATE, timezone: 'Asia/Tehran', slots: body })
    }),
    http.post(api('/bookings/'), async ({ request }) => {
      const body = await request.json()
      calls.created.push(body)
      return createBooking
        ? createBooking(body)
        : HttpResponse.json({ id: 42, status: 'pending', ...body }, { status: 201 })
    }),
  )
}

const prefilled = `/businesses/1/book?service=5&staff=7&date=${DATE}`
const render = (route = prefilled) => renderWithProviders(routes, { route, preloadedState: loggedIn })

async function pickAndBook(user, time) {
  const slots = await screen.findByRole('group', { name: 'Free times' })
  await user.click(within(slots).getByRole('button', { name: time }))
  await user.click(screen.getByRole('button', { name: `Book ${time}` }))
}

describe('booking flow', () => {
  beforeEach(() => backend())

  test('shows free slots in the business timezone and books one', async () => {
    const { user } = render()

    expect(await screen.findByRole('heading', { name: /Free times/ })).toHaveTextContent('Asia/Tehran')
    await pickAndBook(user, '10:00')

    expect(await screen.findByText('My bookings page (new booking #42)')).toBeInTheDocument()
    // The exact instant, with its offset, is what reaches the API.
    expect(calls.created[0]).toEqual({ staff: 7, service: 5, start: `${DATE}T10:00:00+03:30`, notes: '' })
  })

  test('409 slot_unavailable: friendly message, slots refetched, taken slot gone', async () => {
    backend({
      createBooking: () =>
        HttpResponse.json(
          { detail: 'this slot has just been taken', code: 'slot_unavailable' },
          { status: 409 },
        ),
      // First load offers 10:00; after the 409 the server no longer does.
      availability: (n) => (n === 1 ? [slot('10:00'), slot('11:00')] : [slot('11:00')]),
    })
    const { user } = render()

    await pickAndBook(user, '10:00')

    expect(await screen.findByRole('alert')).toHaveTextContent('this slot was just taken')
    // The error renders as soon as the POST fails; the refetched slot list
    // arrives a moment later, so wait for it rather than asserting at once.
    const slots = screen.getByRole('group', { name: 'Free times' })
    await waitFor(() =>
      expect(within(slots).queryByRole('button', { name: '10:00' })).not.toBeInTheDocument(),
    )
    expect(within(slots).getByRole('button', { name: '11:00' })).toBeInTheDocument()
    expect(calls.availability).toBe(2) // refetched because of the 409, not by hand
    // The stale choice is cleared, so it can't be submitted again.
    expect(screen.queryByRole('button', { name: /^Book / })).not.toBeInTheDocument()
  })

  test('other 400s are explained using their error code', async () => {
    backend({
      createBooking: () =>
        HttpResponse.json(
          { detail: "requested time is outside the staff member's working hours", code: 'outside_working_hours' },
          { status: 400 },
        ),
    })
    const { user } = render()

    await pickAndBook(user, '11:00')

    expect(await screen.findByRole('alert')).toHaveTextContent("That time is outside Sara's working hours.")
    expect(calls.availability).toBe(1) // a 400 doesn't make the slot list stale
  })

  test('invalid_request shows the server detail', async () => {
    backend({
      createBooking: () =>
        HttpResponse.json({ detail: 'start must be in the future', code: 'invalid_request' }, { status: 400 }),
    })
    const { user } = render()

    await pickAndBook(user, '10:00')

    expect(await screen.findByRole('alert')).toHaveTextContent('Start must be in the future.')
  })

  test('choosing a service offered by one person picks them automatically', async () => {
    const { user } = render(`/businesses/1/book?date=${DATE}`)

    await user.selectOptions(await screen.findByLabelText('Service'), 'Haircut (60 min)')

    expect(screen.getByLabelText('With')).toHaveValue('7')
    expect(await screen.findByRole('group', { name: 'Free times' })).toBeInTheDocument()
  })

  test('a day without free times says so', async () => {
    backend({ availability: () => [] })
    render()

    expect(await screen.findByText(/No free times on this day/)).toBeInTheDocument()
  })
})
