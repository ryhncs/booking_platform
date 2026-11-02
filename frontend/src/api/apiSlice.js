import { createApi } from '@reduxjs/toolkit/query/react'

import { baseQueryWithReauth } from './baseQuery.js'

/**
 * The single RTK Query "API slice" for the whole app.
 *
 * It starts with no endpoints: each feature adds its own with
 * `apiSlice.injectEndpoints(...)` (see features/<name>/<name>Api.js). That keeps the
 * booking code next to the booking pages while still sharing one cache, one
 * set of tags and one reauth-aware baseQuery.
 *
 * Tags are how the cache stays fresh. A query *provides* tags ("this result
 * contains Booking data"); a mutation *invalidates* tags ("Booking data
 * changed"). RTK Query then refetches every mounted query that provided an
 * invalidated tag, so a list updates after you create something, with no
 * manual refetch calls.
 */
export const apiSlice = createApi({
  reducerPath: 'api',
  baseQuery: baseQueryWithReauth,
  tagTypes: [
    'Me',
    'Business',
    'Staff',
    'Service',
    'WorkingHours',
    'Booking',
    'Availability',
    'Timezone',
  ],
  endpoints: () => ({}),
})
