import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'

import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import { api, server } from '../../test/server.js'

const page = (results, extra = {}) => ({ count: results.length, next: null, previous: null, results, ...extra })
const SALON = { id: 1, owner: 9, name: 'Salon', slug: 'salon', timezone: 'Asia/Tehran' }

function backend(overrides = []) {
  server.use(
    ...overrides,
    http.get(api('/me/'), () => HttpResponse.json({ id: 2, email: 'c@example.com', role: 'customer' })),
    http.get(api('/businesses/'), () => HttpResponse.json(page([SALON]))),
    http.get(api('/businesses/1/'), () => HttpResponse.json(SALON)),
    http.get(api('/services/'), () =>
      HttpResponse.json(
        page([
          { id: 5, business: 1, name: 'Haircut', duration_minutes: 60, price: '250000.00', staff: [7], is_active: true },
          { id: 6, business: 1, name: 'Colour', duration_minutes: 90, price: '400000.00', staff: [], is_active: true },
        ]),
      ),
    ),
    http.get(api('/staff/'), () => HttpResponse.json(page([{ id: 7, business: 1, display_name: 'Sara', is_active: true }]))),
  )
}

describe('catalog', () => {
  test('the home page lists businesses', async () => {
    backend()
    renderWithProviders(undefined, { route: '/', preloadedState: loggedIn })

    expect(await screen.findByRole('heading', { name: 'Salon' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View services' })).toHaveAttribute('href', '/businesses/1')
  })

  test('an empty catalog says so', async () => {
    backend([http.get(api('/businesses/'), () => HttpResponse.json(page([])))])
    renderWithProviders(undefined, { route: '/businesses', preloadedState: loggedIn })

    expect(await screen.findByText(/No businesses yet/)).toBeInTheDocument()
  })

  test('a business shows bookable services with who offers them', async () => {
    backend()
    renderWithProviders(undefined, { route: '/businesses/1', preloadedState: loggedIn })

    const haircut = (await screen.findByText('Haircut')).closest('li')
    expect(within(haircut).getByText(/60 min/)).toHaveTextContent('with Sara')
    expect(within(haircut).getByRole('link', { name: 'Book' })).toHaveAttribute(
      'href',
      '/businesses/1/book?service=5',
    )
    // A service nobody offers can't be booked.
    const colour = screen.getByText('Colour').closest('li')
    expect(within(colour).getByText('Not bookable yet')).toBeInTheDocument()
  })

  test('an unknown business shows a not-found message', async () => {
    backend([http.get(api('/businesses/99/'), () => HttpResponse.json({ detail: 'Not found.' }, { status: 404 }))])
    renderWithProviders(undefined, { route: '/businesses/99', preloadedState: loggedIn })

    expect(await screen.findByRole('alert')).toHaveTextContent("doesn't exist")
  })
})
