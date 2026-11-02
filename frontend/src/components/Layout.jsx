import { useDispatch } from 'react-redux'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { loggedOut } from '../features/auth/authSlice.js'
import { useCurrentUser } from '../features/auth/useCurrentUser.js'

/**
 * The frame around every page: header + nav, then the current page via <Outlet />.
 * React Router renders the matching child route where <Outlet /> sits.
 */
export default function Layout() {
  const { user, isLoggedIn } = useCurrentUser()
  const dispatch = useDispatch()
  const navigate = useNavigate()

  function logout() {
    // store.js reacts to this action by clearing the API cache, and
    // ProtectedRoute redirects anyone left on a protected page.
    dispatch(loggedOut())
    navigate('/login')
  }

  return (
    <>
      <header className="site-header">
        <nav className="container nav" aria-label="Main">
          <NavLink to="/" className="brand">
            Booking Platform
          </NavLink>
          {isLoggedIn && (
            <ul className="nav-links">
              {/* NavLink adds class="active" on the current page automatically. */}
              <li>
                <NavLink to="/businesses">Businesses</NavLink>
              </li>
              <li>
                <NavLink to="/bookings">My bookings</NavLink>
              </li>
              {user?.role === 'owner' && (
                <>
                  <li>
                    <NavLink to="/owner/businesses">My businesses</NavLink>
                  </li>
                  <li>
                    <NavLink to="/owner/bookings">Incoming bookings</NavLink>
                  </li>
                </>
              )}
            </ul>
          )}
          <div className="nav-user">
            {isLoggedIn ? (
              <>
                {user && <span className="muted">{user.email}</span>}
                <button type="button" className="btn btn-small" onClick={logout}>
                  Log out
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login">Log in</NavLink>
                <NavLink to="/register" className="btn btn-small btn-primary">
                  Sign up
                </NavLink>
              </>
            )}
          </div>
        </nav>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  )
}
