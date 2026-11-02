import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { MemoryRouter } from 'react-router-dom'

import AppRoutes from '../AppRoutes.jsx'
import { makeStore } from '../app/store.js'

/** Store state for a logged-in user (the access token gets refreshed on demand). */
export const loggedIn = { auth: { accessToken: 'test-access', refreshToken: 'test-refresh' } }

/**
 * Render UI the way the real app does (Redux store + router) but with a fresh
 * store per test and an in-memory router starting at `route`.
 *
 * By default it renders the app's real routes; pass `ui` to render something else.
 */
export function renderWithProviders(ui = <AppRoutes />, { route = '/', preloadedState } = {}) {
  const store = makeStore(preloadedState)
  // userEvent simulates real typing and clicking (focus, key events, ...).
  const user = userEvent.setup()
  const utils = render(
    <Provider store={store}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </Provider>,
  )
  return { store, user, ...utils }
}
