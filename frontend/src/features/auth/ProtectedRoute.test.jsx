import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, test } from 'vitest'

import { api, server } from '../../test/server.js'
import { loggedIn, renderWithProviders } from '../../test/render.jsx'
import LoginPage from './LoginPage.jsx'
import ProtectedRoute from './ProtectedRoute.jsx'

const CUSTOMER = { id: 1, email: 'ann@example.com', role: 'customer' }

// A tiny route tree that isolates ProtectedRoute from the real pages.
const routes = (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute />}>
      <Route path="/secret" element={<p>Secret page</p>} />
    </Route>
    <Route element={<ProtectedRoute role="owner" />}>
      <Route path="/owner-only" element={<p>Owner page</p>} />
    </Route>
  </Routes>
)

const meReturns = (user) => server.use(http.get(api('/me/'), () => HttpResponse.json(user)))

describe('ProtectedRoute', () => {
  test('redirects a logged-out visitor to the login page', async () => {
    renderWithProviders(routes, { route: '/secret' })

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.queryByText('Secret page')).not.toBeInTheDocument()
  })

  test('after logging in, sends the user back to the page they wanted', async () => {
    server.use(
      http.post(api('/auth/login/'), () => HttpResponse.json({ access: 'a', refresh: 'r' })),
    )
    meReturns(CUSTOMER)
    const { user } = renderWithProviders(routes, { route: '/secret' })

    await user.type(await screen.findByLabelText('Email'), 'ann@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct-horse')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('Secret page')).toBeInTheDocument()
  })

  test('shows a loading state while it finds out who the user is, then the page', async () => {
    meReturns(CUSTOMER)
    renderWithProviders(routes, { route: '/secret', preloadedState: loggedIn })

    expect(screen.getByRole('status')).toHaveTextContent('Loading')
    expect(await screen.findByText('Secret page')).toBeInTheDocument()
  })

  test('a session whose refresh token was revoked ends up on the login page', async () => {
    server.use(
      http.get(api('/me/'), () => HttpResponse.json({ detail: 'expired' }, { status: 401 })),
      http.post(api('/auth/refresh/'), () =>
        HttpResponse.json({ detail: 'Token is invalid' }, { status: 401 }),
      ),
    )
    renderWithProviders(routes, { route: '/secret', preloadedState: loggedIn })

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })

  test('a role-restricted page tells a customer it is for owners', async () => {
    meReturns(CUSTOMER)
    renderWithProviders(routes, { route: '/owner-only', preloadedState: loggedIn })

    expect(await screen.findByRole('alert')).toHaveTextContent('for business owners')
    expect(screen.queryByText('Owner page')).not.toBeInTheDocument()
  })

  test('an owner can open the owner page', async () => {
    meReturns({ ...CUSTOMER, role: 'owner' })
    renderWithProviders(routes, { route: '/owner-only', preloadedState: loggedIn })

    expect(await screen.findByText('Owner page')).toBeInTheDocument()
  })

  test('a server error shows a retryable error instead of a blank page', async () => {
    server.use(http.get(api('/me/'), () => HttpResponse.json({}, { status: 500 })))
    renderWithProviders(routes, { route: '/secret', preloadedState: loggedIn })

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('login and logout through the real app', () => {
  test('wrong credentials show a friendly message', async () => {
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json({ detail: 'No active account found' }, { status: 401 }),
      ),
    )
    const { user } = renderWithProviders(undefined, { route: '/login' })

    await user.type(await screen.findByLabelText('Email'), 'ann@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password.')
  })

  test('logging out returns to the login page and forgets the session', async () => {
    meReturns(CUSTOMER)
    localStorage.setItem('booking.refreshToken', 'test-refresh')
    const { user, store } = renderWithProviders(undefined, { route: '/', preloadedState: loggedIn })

    await user.click(await screen.findByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(store.getState().auth.refreshToken).toBeNull()
    expect(localStorage.getItem('booking.refreshToken')).toBeNull()
  })
})
