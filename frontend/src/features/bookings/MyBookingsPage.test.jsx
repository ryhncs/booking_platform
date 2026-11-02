import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'

import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import { api, server } from '../../test/server.js'

const ME = { id: 2, email: 'cy@example.com', role: 'customer' }
const inAnHour = () => new Date(Date.now() + 60 * 60 * 1000).toISOString()

const booking = (overrides) => ({
  id: 1,
  customer: ME.id,
  customer_name: 'Cy',
  business: 1,
  business_name: 'Salon',
  business_timezone: 'Asia/Tehran',
  staff: 7,
  staff_name: 'Sara',
  service: 5,
  service_name: 'Haircut',
  start: '2030-01-07T06:30:00Z', // 10:00 in Tehran
  end: '2030-01-07T07:30:00Z',
  status: 'pending',
  expires_at: inAnHour(),
  notes: '',
  cancelled_by: null,
  cancellation_reason: '',
  created_at: '2030-01-01T00:00:00Z',
  ...overrides,
})

/** A tiny in-memory backend: confirm/cancel change what the list returns next. */
function backend(initial) {
  const db = { bookings: initial, listCalls: 0, lastQuery: null, cancelBody: null }
  server.use(
    http.get(api('/me/'), () => HttpResponse.json(ME)),
    http.get(api('/bookings/'), ({ request }) => {
      db.listCalls += 1
      db.lastQuery = new URL(request.url).searchParams
      const status = db.lastQuery.get('status')
      const results = db.bookings.filter((b) => !status || b.status === status)
      return HttpResponse.json({ count: results.length, next: null, previous: null, results })
    }),
    http.post(api('/bookings/:id/confirm/'), ({ params }) => {
      const b = db.bookings.find((x) => x.id === Number(params.id))
      Object.assign(b, { status: 'confirmed', expires_at: null })
      return HttpResponse.json(b)
    }),
    http.post(api('/bookings/:id/cancel/'), async ({ params, request }) => {
      db.cancelBody = await request.json()
      const b = db.bookings.find((x) => x.id === Number(params.id))
      Object.assign(b, { status: 'cancelled', cancelled_by: ME.id, cancellation_reason: db.cancelBody.reason })
      return HttpResponse.json(b)
    }),
  )
  return db
}

const render = () => renderWithProviders(undefined, { route: '/bookings', preloadedState: loggedIn })

describe('My bookings', () => {
  test('lists only my own bookings, in the business timezone', async () => {
    const db = backend([booking()])
    render()

    const card = (await screen.findByText('Haircut')).closest('li')
    expect(within(card).getByText(/10:00–11:00/)).toHaveTextContent('Asia/Tehran')
    expect(db.lastQuery.get('scope')).toBe('mine')
  })

  test('confirming updates the card through a refetch', async () => {
    const db = backend([booking()])
    const { user } = render()

    await user.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(await screen.findByText('confirmed')).toBeInTheDocument()
    expect(db.listCalls).toBe(2) // invalidated tags refetched the list
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })

  test('cancelling with a reason sends it and shows who cancelled and why', async () => {
    const db = backend([booking({ status: 'confirmed', expires_at: null })])
    const { user } = render()

    await user.click(await screen.findByRole('button', { name: 'Cancel…' }))
    await user.type(screen.getByLabelText(/Reason/), 'Feeling unwell')
    await user.click(screen.getByRole('button', { name: 'Cancel booking' }))

    expect(await screen.findByText('Cancelled by you: “Feeling unwell”')).toBeInTheDocument()
    expect(db.cancelBody).toEqual({ reason: 'Feeling unwell' })
  })

  test('the reason is optional and "Keep booking" backs out', async () => {
    const db = backend([booking()])
    const { user } = render()

    await user.click(await screen.findByRole('button', { name: 'Cancel…' }))
    await user.click(screen.getByRole('button', { name: 'Keep booking' }))
    expect(db.cancelBody).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Cancel…' }))
    await user.click(screen.getByRole('button', { name: 'Cancel booking' }))
    expect(await screen.findByText('Cancelled by you.')).toBeInTheDocument()
    expect(db.cancelBody).toEqual({ reason: '' })
  })

  test.each([
    [{ cancelled_by: 9, cancellation_reason: 'Stylist is ill' }, 'Cancelled by the business: “Stylist is ill”'],
    [{ cancelled_by: null, cancellation_reason: 'Hold expired' }, 'Cancelled by the system (the reservation hold expired): “Hold expired”'],
  ])('shows who cancelled: %o', async (fields, text) => {
    backend([booking({ status: 'cancelled', expires_at: null, ...fields })])
    render()

    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel…' })).not.toBeInTheDocument()
  })

  test('an expired hold cannot be confirmed from the UI', async () => {
    backend([booking({ expires_at: new Date(Date.now() - 60_000).toISOString() })])
    render()

    expect(await screen.findByText(/hold has expired/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })

  test('a failed confirm explains why', async () => {
    backend([booking()])
    server.use(
      http.post(api('/bookings/:id/confirm/'), () =>
        HttpResponse.json({ detail: 'the hold on this booking has expired', code: 'invalid_request' }, { status: 400 }),
      ),
    )
    const { user } = render()

    await user.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The hold on this booking has expired.')
  })

  test('the status filter asks the API for that status', async () => {
    const db = backend([booking(), booking({ id: 2, service_name: 'Shave', status: 'cancelled' })])
    const { user } = render()
    expect(await screen.findByText('Shave')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Pending' }))

    // The previous results stay on screen (faded) until the new ones arrive,
    // so wait for the cancelled booking to go rather than for Haircut to appear.
    await waitFor(() => expect(screen.queryByText('Shave')).not.toBeInTheDocument())
    expect(screen.getByText('Haircut')).toBeInTheDocument()
    expect(db.lastQuery.get('status')).toBe('pending')
  })

  test('no bookings yet shows a way to start', async () => {
    backend([])
    render()

    expect(await screen.findByText(/No bookings yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Find a business' })).toHaveAttribute('href', '/businesses')
  })
})
