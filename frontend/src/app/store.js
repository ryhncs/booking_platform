import { configureStore, createListenerMiddleware } from '@reduxjs/toolkit'

import { apiSlice } from '../api/apiSlice.js'
import authReducer, { loggedOut, REFRESH_TOKEN_KEY } from '../features/auth/authSlice.js'

/**
 * Creates a new Redux store. A factory (rather than one global store) lets
 * every test start from a clean store with its own preloaded state.
 */
export function makeStore(preloadedState) {
  // Listener middleware runs side effects in response to actions, keeping
  // reducers pure.
  const listener = createListenerMiddleware()
  listener.startListening({
    actionCreator: loggedOut,
    // Throw away every cached response: the next user must never see the
    // previous user's bookings.
    effect: (_action, api) => api.dispatch(apiSlice.util.resetApiState()),
  })

  const store = configureStore({
    reducer: {
      auth: authReducer,
      // RTK Query keeps its cache in the store under reducerPath ("api").
      [apiSlice.reducerPath]: apiSlice.reducer,
    },
    // The API middleware handles caching, refetching and cache lifetimes.
    middleware: (getDefault) => getDefault().prepend(listener.middleware).concat(apiSlice.middleware),
    preloadedState,
  })

  // Mirror the refresh token into localStorage whenever it changes, so a page
  // reload keeps you logged in.
  let savedToken = store.getState().auth.refreshToken
  store.subscribe(() => {
    const token = store.getState().auth.refreshToken
    if (token === savedToken) return
    savedToken = token
    try {
      if (token) localStorage.setItem(REFRESH_TOKEN_KEY, token)
      else localStorage.removeItem(REFRESH_TOKEN_KEY)
    } catch {
      // Storage unavailable: the session just won't survive a reload.
    }
  })

  return store
}
