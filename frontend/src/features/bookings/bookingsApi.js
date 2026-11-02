import { apiSlice } from '../../api/apiSlice.js'
import { listTags, qs } from '../businesses/businessesApi.js'

// Any change to a booking can change which slots are free, so every booking
// mutation invalidates 'Availability' and every mounted availability query
// refetches. (Confirming doesn't actually free or take a slot; it's included
// to keep the rule simple: "a booking changed, so refresh availability".)
const bookingChanged = (id) => [{ type: 'Booking', id }, { type: 'Booking', id: 'LIST' }, 'Availability']

export const bookingsApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    getAvailability: build.query({
      query: ({ staff, service, date }) => `/availability/${qs({ staff, service, date })}`,
      providesTags: ['Availability'],
      // Free slots go stale quickly (other people book them), so don't serve
      // a cached copy older than 30 seconds when the page is opened again.
      keepUnusedDataFor: 30,
    }),

    listBookings: build.query({
      query: ({ scope, status, page } = {}) => `/bookings/${qs({ scope, status, page })}`,
      providesTags: listTags('Booking'),
    }),

    createBooking: build.mutation({
      query: (body) => ({ url: '/bookings/', method: 'POST', body }),
      // invalidatesTags can be a function of the outcome. On success the new
      // booking must show up in lists, and the slot is gone. On 409 (someone
      // else just took the slot) our slot list is out of date, so refresh it
      // to show the real free times. Other errors change nothing.
      invalidatesTags: (result, error) => {
        if (result) return [{ type: 'Booking', id: 'LIST' }, 'Availability']
        if (error?.status === 409) return ['Availability']
        return []
      },
    }),

    confirmBooking: build.mutation({
      query: (id) => ({ url: `/bookings/${id}/confirm/`, method: 'POST' }),
      // Even a failed confirm (e.g. the hold expired) means our copy of the
      // booking may be stale, so refetch it either way.
      invalidatesTags: (_result, _error, id) => bookingChanged(id),
    }),

    cancelBooking: build.mutation({
      query: ({ id, reason }) => ({
        url: `/bookings/${id}/cancel/`,
        method: 'POST',
        body: { reason: reason ?? '' },
      }),
      invalidatesTags: (_result, _error, { id }) => bookingChanged(id),
    }),
  }),
})

export const {
  useGetAvailabilityQuery,
  useListBookingsQuery,
  useCreateBookingMutation,
  useConfirmBookingMutation,
  useCancelBookingMutation,
} = bookingsApi
