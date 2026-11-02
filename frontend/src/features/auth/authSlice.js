import { createSlice } from '@reduxjs/toolkit'

// Only the refresh token is persisted. The access token is short-lived
// (15 min) and kept in memory: after a page reload the first API call gets a
// 401 and the reauth logic in baseQuery.js quietly fetches a new one.
//
// Trade-off worth knowing: anything in localStorage can be read by JavaScript
// on this origin, so an XSS bug could steal the refresh token. An httpOnly
// cookie avoids that but needs CSRF protection on the Django side. For this
// project localStorage keeps the auth flow easy to follow.
export const REFRESH_TOKEN_KEY = 'booking.refreshToken'

function loadRefreshToken() {
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    return null // storage can be blocked (private mode, strict settings)
  }
}

const authSlice = createSlice({
  name: 'auth',
  // A function, not an object: it runs each time a store is created, so every
  // test (and every page load) reads localStorage fresh.
  initialState: () => ({ accessToken: null, refreshToken: loadRefreshToken() }),
  reducers: {
    // Reducers must be pure, so they only update state. Saving to
    // localStorage happens in store.js, which watches this slice.
    credentialsReceived(state, action) {
      const { access, refresh } = action.payload
      state.accessToken = access
      // A token refresh returns only `access`; keep the refresh token we have.
      if (refresh) state.refreshToken = refresh
    },
    loggedOut() {
      return { accessToken: null, refreshToken: null }
    },
  },
})

export const { credentialsReceived, loggedOut } = authSlice.actions
export default authSlice.reducer

// Selectors: small functions that read one thing from the store. Components
// use them with useSelector so they don't depend on the state's exact shape.
export const selectAccessToken = (state) => state.auth.accessToken
export const selectRefreshToken = (state) => state.auth.refreshToken
// Holding a refresh token means we can always get a fresh access token, so
// that is what "logged in" means here.
export const selectIsLoggedIn = (state) => Boolean(state.auth.refreshToken)
