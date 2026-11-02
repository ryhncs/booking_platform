import { fetchBaseQuery } from '@reduxjs/toolkit/query/react'

import { credentialsReceived, loggedOut } from '../features/auth/authSlice.js'

// Every request goes to /api on the page's own origin. In development that is
// the Vite server, which proxies to Django (see vite.config.js). The absolute
// URL (rather than just "/api") also works in tests, where Node's fetch
// can't resolve relative URLs.
const rawBaseQuery = fetchBaseQuery({
  baseUrl: `${window.location.origin}/api`,
  // Runs before every request: attach the access token if we have one.
  prepareHeaders: (headers, { getState }) => {
    const token = getState().auth.accessToken
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return headers
  },
})

// Login/register/refresh answer 401 for wrong credentials. Refreshing and
// retrying those would be pointless (and could loop), so they are excluded.
const isAuthRequest = (args) => {
  const url = typeof args === 'string' ? args : args.url
  return url.startsWith('/auth/')
}

// The refresh request currently in flight, shared by everyone who needs it.
// If five requests get a 401 at once, they all wait for ONE refresh instead
// of firing five.
let refreshInFlight = null

/**
 * Like fetchBaseQuery, but on a 401 it refreshes the access token once and
 * retries the original request.
 *
 * RTK Query calls this for every endpoint (see apiSlice.js), so components
 * never deal with tokens or 401s themselves.
 */
export async function baseQueryWithReauth(args, api, extraOptions) {
  const tokenUsed = api.getState().auth.accessToken
  let result = await rawBaseQuery(args, api, extraOptions)

  if (result.error?.status !== 401 || isAuthRequest(args)) return result
  const refreshToken = api.getState().auth.refreshToken
  if (!refreshToken) return result // not logged in: nothing to refresh with

  // Another request may have refreshed while this one was in flight. If the
  // token has already changed, just retry with the new one.
  if (api.getState().auth.accessToken === tokenUsed) {
    refreshInFlight ??= refreshAccessToken(refreshToken, api, extraOptions).finally(() => {
      refreshInFlight = null
    })
    const refreshed = await refreshInFlight
    if (!refreshed) return result
  }

  // Retry once. If this is still a 401 we return it rather than loop.
  return rawBaseQuery(args, api, extraOptions)
}

async function refreshAccessToken(refreshToken, api, extraOptions) {
  const response = await rawBaseQuery(
    { url: '/auth/refresh/', method: 'POST', body: { refresh: refreshToken } },
    api,
    extraOptions,
  )
  if (response.data?.access) {
    api.dispatch(credentialsReceived({ access: response.data.access }))
    return true
  }
  // Only log out when the server says the refresh token itself is no good
  // (expired or invalid). A network blip or a 500 shouldn't sign you out.
  const status = response.error?.status
  if (status === 401 || status === 400) api.dispatch(loggedOut())
  return false
}
