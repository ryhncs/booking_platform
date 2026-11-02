import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { ErrorMessage, Loading } from '../../components/Status.jsx'
import { useCurrentUser } from './useCurrentUser.js'

/**
 * Wraps routes that need a signed-in user (optionally with a given role).
 *
 * Used as a "layout route": <Route element={<ProtectedRoute />}> ...children.
 * Children render through <Outlet /> only once we know who the user is.
 *
 * This is a UX guard, not security: the API enforces permissions on every
 * request regardless of what the UI shows.
 */
export default function ProtectedRoute({ role }) {
  const location = useLocation()
  const { isLoggedIn, user, isLoading, error, refetch } = useCurrentUser()

  if (!isLoggedIn) {
    // Remember where the user was going so login can send them back there.
    // `replace` stops the Back button from bouncing them to this page again.
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  if (isLoading || !user) {
    if (error) return <ErrorMessage error={error} onRetry={refetch} />
    return <Loading />
  }
  if (role && user.role !== role) {
    return (
      <ErrorMessage>
        This page is for business owners. Register an owner account to manage a business.
      </ErrorMessage>
    )
  }
  return <Outlet />
}
