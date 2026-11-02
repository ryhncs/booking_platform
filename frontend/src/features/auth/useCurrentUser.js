import { useSelector } from 'react-redux'

import { useGetMeQuery } from './authApi.js'
import { selectIsLoggedIn } from './authSlice.js'

/**
 * The signed-in user ({ id, email, role, ... }) plus loading/error flags.
 *
 * Any number of components can call this: RTK Query deduplicates, so /me/ is
 * fetched once and shared from the cache. `skip` avoids a pointless 401
 * request when nobody is logged in.
 */
export function useCurrentUser() {
  const isLoggedIn = useSelector(selectIsLoggedIn)
  const query = useGetMeQuery(undefined, { skip: !isLoggedIn })
  return { ...query, user: query.data ?? null, isLoggedIn }
}
