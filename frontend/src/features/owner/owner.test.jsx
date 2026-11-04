import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, test, vi } from 'vitest'

import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import { api, server } from '../../test/server.js'

const OWNER = { id: 9, email: 'o@example.com', role: 'owner' }
const page = (results) => ({ count: results.length, next: null, previous: null, results })
const SALON = { id: 1, owner: OWNER.id, name: 'Salon', slug: 'salon', timezone: 'Asia/Tehran' }

function backend(extra = []) {
  const db = { created: null, shifts: [], shiftPosts: 0 }
  server.use(
    ...extra,
    http.get(api('/me/'), () => HttpResponse.json(OWNER)),
    http.get(api('/timezones/'), () => HttpResponse.json(['Asia/Tehran', 'Europe/Berlin', 'UTC'])),
    http.get(api('/businesses/'), () => HttpResponse.json(page(db.created ? [db.created] : []))),
    http.post(api('/businesses/'), async ({ request }) => {
      db.created = { id: 2, owner: OWNER.id, ...(await request.json()) }
      return HttpResponse.json(db.created, { status: 201 })
    }),
    http.get(api('/businesses/:id/'), ({ params }) =>
      HttpResponse.json(Number(params.id) === 2 ? db.created : SALON),
    ),
    http.get(api('/staff/'), () => HttpResponse.json(page([{ id: 7, business: 1, display_name: 'Sara', is_active: true }]))),
    http.get(api('/services/'), () => HttpResponse.json(page([]))),
    http.get(api('/working-hours/'), () => HttpResponse.json(page(db.shifts))),
    http.post(api('/working-hours/bulk/'), async ({ request }) => {
      db.shiftPosts += 1
      const body = await request.json()
      const clashing = body.weekdays.filter((day) => db.shifts.some((s) => s.weekday === day))
      if (clashing.length) {
        return HttpResponse.json({ weekdays: ['Overlaps existing hours on Monday. Nothing was added.'] }, { status: 400 })
      }
      const created = body.weekdays.map((weekday, i) => ({
        id: db.shifts.length + i + 1,
        staff: 7,
        weekday,
        start_time: `${body.start_time}:00`,
        end_time: `${body.end_time}:00`,
      }))
      db.shifts.push(...created)
      return HttpResponse.json(created, { status: 201 })
    }),
  )
  return db
}

const render = (route) => renderWithProviders(undefined, { route, preloadedState: loggedIn })

describe('owner: businesses', () => {
  test('a new owner is invited to create a business, with a timezone picker', async () => {
    const db = backend()
    const { user } = render('/owner/businesses')

    await user.type(await screen.findByLabelText('Name'), 'Studio Nine')
    expect(screen.getByLabelText('Web address (slug)')).toHaveValue('studio-nine')
    await user.selectOptions(screen.getByLabelText(/Timezone/), 'Europe/Berlin')
    await user.click(screen.getByRole('button', { name: 'Create business' }))

    // Lands on the new business's management page. (Match the page's h1: the
    // refreshed list briefly shows a "Studio Nine" card heading before the
    // navigation, and that one disappears.)
    expect(await screen.findByRole('heading', { level: 1, name: 'Studio Nine' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See it as a customer' })).toHaveAttribute('href', '/businesses/2')
    expect(db.created).toMatchObject({ name: 'Studio Nine', slug: 'studio-nine', timezone: 'Europe/Berlin' })
  })

  test('field errors from the API appear next to the field', async () => {
    backend([
      http.post(api('/businesses/'), () =>
        HttpResponse.json({ slug: ['business with this slug already exists.'] }, { status: 400 }),
      ),
    ])
    const { user } = render('/owner/businesses')

    await user.type(await screen.findByLabelText('Name'), 'Salon')
    await user.click(screen.getByRole('button', { name: 'Create business' }))

    expect(await screen.findByText('business with this slug already exists.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Web address \(slug\)/)).toHaveAttribute('aria-invalid', 'true')
  })

  test("an owner can't manage someone else's business", async () => {
    backend([http.get(api('/businesses/5/'), () => HttpResponse.json({ ...SALON, id: 5, owner: 123 }))])
    render('/owner/businesses/5')

    expect(await screen.findByRole('alert')).toHaveTextContent('only manage your own')
  })
})

describe('owner: staff and hours', () => {
  test('adding hours shows them; an overlapping shift shows the API message', async () => {
    const db = backend()
    const { user } = render('/owner/businesses/1')

    await user.click(await screen.findByRole('button', { name: 'Hours' }))
    const form = await screen.findByRole('form', { name: 'Add hours for Sara' })
    await user.click(within(form).getByRole('checkbox', { name: 'Monday' }))
    await user.click(within(form).getByRole('button', { name: 'Add hours' }))
    const monday = () => screen.getByRole('rowheader', { name: 'Monday' }).closest('tr')
    await waitFor(() => expect(monday()).toHaveTextContent('09:00–17:00'))

    await user.click(within(form).getByRole('checkbox', { name: 'Monday' }))
    await user.click(within(form).getByRole('button', { name: 'Add hours' }))
    expect(await screen.findByText(/Overlaps existing hours on Monday/)).toBeInTheDocument()
    expect(db.shiftPosts).toBe(2)
  })

  test('deleting staff who still have bookings suggests deactivating instead', async () => {
    backend([http.delete(api('/staff/7/'), () => HttpResponse.json({ detail: 'Cannot delete: it still has bookings.' }, { status: 409 }))])
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { user } = render('/owner/businesses/1')

    await user.click(await screen.findByRole('button', { name: 'Delete' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Deactivate them instead')
  })

  test('customers cannot open owner pages', async () => {
    backend([http.get(api('/me/'), () => HttpResponse.json({ id: 2, email: 'c@example.com', role: 'customer' }))])
    render('/owner/businesses')

    expect(await screen.findByRole('alert')).toHaveTextContent('for business owners')
  })
})
