import { apiSlice } from '../../api/apiSlice.js'

// Owner-only writes. The matching reads live in businessesApi.js; these
// mutations invalidate the tags those reads provide, so lists update by
// themselves after every change.
//
// Almost everything an owner edits (shifts, services, staff, the business
// timezone) changes which slots are free, so most mutations also invalidate
// 'Availability'. The backend clears its Redis cache for the same reasons.

const changed = (type, id) => [{ type, id }, { type, id: 'LIST' }, 'Availability']

export const ownerApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    createBusiness: build.mutation({
      query: (body) => ({ url: '/businesses/', method: 'POST', body }),
      invalidatesTags: [{ type: 'Business', id: 'LIST' }],
    }),
    updateBusiness: build.mutation({
      // PATCH sends only the fields that changed.
      query: ({ id, ...patch }) => ({ url: `/businesses/${id}/`, method: 'PATCH', body: patch }),
      invalidatesTags: (_r, _e, { id }) => changed('Business', id),
    }),

    createStaff: build.mutation({
      query: (body) => ({ url: '/staff/', method: 'POST', body }),
      invalidatesTags: [{ type: 'Staff', id: 'LIST' }],
    }),
    updateStaff: build.mutation({
      query: ({ id, ...patch }) => ({ url: `/staff/${id}/`, method: 'PATCH', body: patch }),
      invalidatesTags: (_r, _e, { id }) => changed('Staff', id),
    }),
    deleteStaff: build.mutation({
      query: (id) => ({ url: `/staff/${id}/`, method: 'DELETE' }),
      // Deleting a person also removes them from every service's staff list.
      invalidatesTags: (_r, _e, id) => [...changed('Staff', id), { type: 'Service', id: 'LIST' }],
    }),

    createService: build.mutation({
      query: (body) => ({ url: '/services/', method: 'POST', body }),
      invalidatesTags: [{ type: 'Service', id: 'LIST' }, 'Availability'],
    }),
    updateService: build.mutation({
      query: ({ id, ...patch }) => ({ url: `/services/${id}/`, method: 'PATCH', body: patch }),
      invalidatesTags: (_r, _e, { id }) => changed('Service', id),
    }),
    deleteService: build.mutation({
      query: (id) => ({ url: `/services/${id}/`, method: 'DELETE' }),
      invalidatesTags: (_r, _e, id) => changed('Service', id),
    }),

    // One request for the same hours on several days: { staff, weekdays: [0..6],
    // start_time, end_time }. The server saves all of them or none.
    bulkCreateWorkingHours: build.mutation({
      query: (body) => ({ url: '/working-hours/bulk/', method: 'POST', body }),
      invalidatesTags: [{ type: 'WorkingHours', id: 'LIST' }, 'Availability'],
    }),
    deleteWorkingHours: build.mutation({
      query: (id) => ({ url: `/working-hours/${id}/`, method: 'DELETE' }),
      invalidatesTags: (_r, _e, id) => changed('WorkingHours', id),
    }),
  }),
})

export const {
  useCreateBusinessMutation,
  useUpdateBusinessMutation,
  useCreateStaffMutation,
  useUpdateStaffMutation,
  useDeleteStaffMutation,
  useCreateServiceMutation,
  useUpdateServiceMutation,
  useDeleteServiceMutation,
  useBulkCreateWorkingHoursMutation,
  useDeleteWorkingHoursMutation,
} = ownerApi
