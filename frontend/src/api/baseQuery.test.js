import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, test } from 'vitest'

import { makeStore } from '../app/store.js'
import { authApi } from '../features/auth/authApi.js'
import { REFRESH_TOKEN_KEY } from '../features/auth/authSlice.js'
import { api, server } from '../test/server.js'
import { apiSlice } from './apiSlice.js'

// A second endpoint, so we can fire two requests at once.
const testApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({ ping: build.query({ query: () => '/ping/' }) }),
  overrideExisting: true,
})

const ME = { id: 1, email: 'ann@example.com', role: 'customer' }

/** Endpoints that only accept the token "fresh-access" and count refreshes. */
function mockBackend({ refresh = () => HttpResponse.json({ access: 'fresh-access' }) } = {}) {
  const calls = { refresh: 0, refreshBodies: [] }
  const authorised = (handler) => ({ request }) =>
    request.headers.get('Authorization') === 'Bearer fresh-access'
      ? handler()
      : HttpResponse.json({ detail: 'Token is invalid or expired' }, { status: 401 })

  server.use(
    http.get(api('/me/'), authorised(() => HttpResponse.json(ME))),
    http.get(api('/ping/'), authorised(() => HttpResponse.json({ ok: true }))),
    http.post(api('/auth/refresh/'), async ({ request }) => {
      calls.refresh += 1
      calls.refreshBodies.push(await request.json())
      return refresh()
    }),
  )
  return calls
}

const loggedInStore = () =>
  makeStore({ auth: { accessToken: 'expired-access', refreshToken: 'refresh-1' } })

describe('baseQueryWithReauth', () => {
  test('on 401 it refreshes the access token and retries the request', async () => {
    const calls = mockBackend()
    const store = loggedInStore()

    const result = await store.dispatch(authApi.endpoints.getMe.initiate())

    expect(result.data).toEqual(ME)
    expect(calls.refresh).toBe(1)
    expect(calls.refreshBodies[0]).toEqual({ refresh: 'refresh-1' })
    expect(store.getState().auth.accessToken).toBe('fresh-access')
    expect(store.getState().auth.refreshToken).toBe('refresh-1') // kept
  })

  test('parallel 401s share a single refresh', async () => {
    const calls = mockBackend()
    const store = loggedInStore()

    const [me, ping] = await Promise.all([
      store.dispatch(authApi.endpoints.getMe.initiate()),
      store.dispatch(testApi.endpoints.ping.initiate()),
    ])

    expect(me.data).toEqual(ME)
    expect(ping.data).toEqual({ ok: true })
    expect(calls.refresh).toBe(1)
  })

  test('a rejected refresh token logs the user out and clears storage', async () => {
    const calls = mockBackend({
      refresh: () => HttpResponse.json({ detail: 'Token is blacklisted' }, { status: 401 }),
    })
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-1')
    const store = makeStore()
    expect(store.getState().auth.refreshToken).toBe('refresh-1') // loaded from storage

    const result = await store.dispatch(authApi.endpoints.getMe.initiate())

    // Logging out resets the whole API cache (store.js), which also discards
    // this in-flight request: no data, and nothing cached for the next user.
    expect(result.data).toBeUndefined()
    expect(calls.refresh).toBe(1)
    expect(store.getState().auth).toEqual({ accessToken: null, refreshToken: null })
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull()
  })

  test('a network failure during refresh does not log the user out', async () => {
    mockBackend({ refresh: () => HttpResponse.error() })
    const store = loggedInStore()

    const result = await store.dispatch(authApi.endpoints.getMe.initiate())

    expect(result.error.status).toBe(401)
    expect(store.getState().auth.refreshToken).toBe('refresh-1')
  })

  test('without a refresh token a 401 is returned as is', async () => {
    const calls = mockBackend()
    const store = makeStore()

    const result = await store.dispatch(authApi.endpoints.getMe.initiate())

    expect(result.error.status).toBe(401)
    expect(calls.refresh).toBe(0)
  })

  test('a wrong password on login does not trigger a refresh', async () => {
    const calls = mockBackend()
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json({ detail: 'No active account found' }, { status: 401 }),
      ),
    )
    const store = loggedInStore()

    const result = await store.dispatch(
      authApi.endpoints.login.initiate({ email: 'ann@example.com', password: 'nope' }),
    )

    expect(result.error.status).toBe(401)
    expect(calls.refresh).toBe(0)
  })
})

describe('auth state', () => {
  beforeEach(() => localStorage.clear())

  test('login stores both tokens and persists only the refresh token', async () => {
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json({ access: 'access-1', refresh: 'refresh-1' }),
      ),
    )
    const store = makeStore()

    await store.dispatch(
      authApi.endpoints.login.initiate({ email: 'ann@example.com', password: 'pw' }),
    )

    expect(store.getState().auth).toEqual({ accessToken: 'access-1', refreshToken: 'refresh-1' })
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-1')
    expect(JSON.stringify(localStorage)).not.toContain('access-1')
  })

  test('logging out clears the cached API data', async () => {
    mockBackend()
    const store = makeStore({ auth: { accessToken: 'fresh-access', refreshToken: 'r' } })
    await store.dispatch(authApi.endpoints.getMe.initiate())
    expect(authApi.endpoints.getMe.select()(store.getState()).data).toEqual(ME)

    const { loggedOut } = await import('../features/auth/authSlice.js')
    store.dispatch(loggedOut())

    expect(authApi.endpoints.getMe.select()(store.getState()).data).toBeUndefined()
  })
})
