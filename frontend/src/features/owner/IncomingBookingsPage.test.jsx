import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'

import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import { api, server } from '../../test/server.js'

const OWNER = { id: 9, email: 'o@example.com', role: 'owner' }

test('owner sees bookings at their business, confirms one and cancels another with a reason', async () => {
  const bookings = [
    { id: 1, customer: 2, customer_name: 'Cy Rus', status: 'pending', service_name: 'Haircut' },
    { id: 2, customer: 3, customer_name: 'Di Ana', status: 'confirmed', service_name: 'Colour' },
  ].map((b) => ({
    business: 1,
    business_name: 'Salon',
    business_timezone: 'Asia/Tehran',
    staff: 7,
    staff_name: 'Sara',
    service: 5,
    start: '2030-01-07T06:30:00Z',
    end: '2030-01-07T07:30:00Z',
    expires_at: b.status === 'pending' ? new Date(Date.now() + 600_000).toISOString() : null,
    notes: '',
    cancelled_by: null,
    cancellation_reason: '',
    ...b,
  }))
  let scope
  server.use(
    http.get(api('/me/'), () => HttpResponse.json(OWNER)),
    http.get(api('/bookings/'), ({ request }) => {
      scope = new URL(request.url).searchParams.get('scope')
      return HttpResponse.json({ count: 2, next: null, previous: null, results: bookings })
    }),
    http.post(api('/bookings/1/confirm/'), () => {
      Object.assign(bookings[0], { status: 'confirmed', expires_at: null })
      return HttpResponse.json(bookings[0])
    }),
    http.post(api('/bookings/2/cancel/'), async ({ request }) => {
      const { reason } = await request.json()
      Object.assign(bookings[1], { status: 'cancelled', cancelled_by: OWNER.id, cancellation_reason: reason })
      return HttpResponse.json(bookings[1])
    }),
  )
  const { user } = renderWithProviders(undefined, { route: '/owner/bookings', preloadedState: loggedIn })

  const first = (await screen.findByText('Customer: Cy Rus')).closest('li')
  const second = screen.getByText('Customer: Di Ana').closest('li')
  expect(scope).toBe('business')

  await user.click(within(first).getByRole('button', { name: 'Confirm' }))
  expect(await within(first).findByText('confirmed')).toBeInTheDocument()

  await user.click(within(second).getByRole('button', { name: 'Cancel…' }))
  // The owner is told the reason goes to the customer.
  await user.type(within(second).getByLabelText(/shared with the customer/), 'Stylist is ill')
  await user.click(within(second).getByRole('button', { name: 'Cancel booking' }))
  expect(await within(second).findByText('Cancelled by you: “Stylist is ill”')).toBeInTheDocument()
})
