import { apiSlice } from '../../api/apiSlice.js'

// Builds a query string, leaving out empty values: { business: 3, page: undefined } -> "?business=3"
export function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// Tag helpers for paginated DRF lists ({ count, next, previous, results }).
// Each item gets its own tag, plus a 'LIST' tag that mutations can invalidate
// when something is created (a new item isn't in any existing tag yet).
export const listTags = (type) => (result) => [
  ...(result?.results ?? []).map(({ id }) => ({ type, id })),
  { type, id: 'LIST' },
]

export const businessesApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    listBusinesses: build.query({
      query: ({ page, mine } = {}) => `/businesses/${qs({ page, mine: mine ? 'true' : undefined })}`,
      providesTags: listTags('Business'),
    }),
    getBusiness: build.query({
      query: (id) => `/businesses/${id}/`,
      providesTags: (_result, _error, id) => [{ type: 'Business', id }],
    }),
    // Staff/services/shifts lists are small (page size is 50), so pages fetch
    // the first page only.
    listStaff: build.query({
      query: ({ business }) => `/staff/${qs({ business })}`,
      providesTags: listTags('Staff'),
    }),
    listServices: build.query({
      query: ({ business, staff } = {}) => `/services/${qs({ business, staff })}`,
      providesTags: listTags('Service'),
    }),
    listWorkingHours: build.query({
      query: ({ staff }) => `/working-hours/${qs({ staff })}`,
      providesTags: listTags('WorkingHours'),
    }),
    listTimezones: build.query({
      query: () => '/timezones/',
      // The list never changes while the app runs: keep it for an hour.
      keepUnusedDataFor: 60 * 60,
      providesTags: ['Timezone'],
    }),
  }),
})

export const {
  useListBusinessesQuery,
  useGetBusinessQuery,
  useListStaffQuery,
  useListServicesQuery,
  useListWorkingHoursQuery,
  useListTimezonesQuery,
} = businessesApi
