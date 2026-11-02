import { apiSlice } from '../../api/apiSlice.js'
import { credentialsReceived } from './authSlice.js'

export const authApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    login: build.mutation({
      query: ({ email, password }) => ({
        url: '/auth/login/',
        method: 'POST',
        body: { email, password },
      }),
      // onQueryStarted lets an endpoint react to its own result. Here: when
      // login succeeds, store the tokens so every later request is authenticated.
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled
          dispatch(credentialsReceived(data))
        } catch {
          // The component shows the error from the mutation hook itself.
        }
      },
    }),

    register: build.mutation({
      query: (body) => ({ url: '/auth/register/', method: 'POST', body }),
    }),

    // Who am I? Used for the nav bar and for role checks (customer vs owner).
    getMe: build.query({
      query: () => '/me/',
      providesTags: ['Me'],
    }),
  }),
})

// RTK Query generates a React hook per endpoint: use<Name>Query / use<Name>Mutation.
export const { useLoginMutation, useRegisterMutation, useGetMeQuery } = authApi
