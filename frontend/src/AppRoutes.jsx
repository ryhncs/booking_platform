import { Link, Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout.jsx'
import LoginPage from './features/auth/LoginPage.jsx'
import ProtectedRoute from './features/auth/ProtectedRoute.jsx'
import RegisterPage from './features/auth/RegisterPage.jsx'
import BusinessDetailPage from './features/businesses/BusinessDetailPage.jsx'
import BusinessesPage from './features/businesses/BusinessesPage.jsx'
import BookingPage from './features/bookings/BookingPage.jsx'
import MyBookingsPage from './features/bookings/MyBookingsPage.jsx'

/**
 * Every page of the app and the URL it lives at.
 *
 * Nesting matters: a parent route with an `element` but no `path` (Layout,
 * ProtectedRoute) is a wrapper. It renders around its children, which appear
 * where the wrapper renders <Outlet />.
 */
export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Everything below needs a signed-in user. */}
        <Route element={<ProtectedRoute />}>
          <Route index element={<Navigate to="/businesses" replace />} />
          <Route path="/businesses" element={<BusinessesPage />} />
          <Route path="/businesses/:businessId" element={<BusinessDetailPage />} />
          <Route path="/businesses/:businessId/book" element={<BookingPage />} />
          <Route path="/bookings" element={<MyBookingsPage />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

function NotFound() {
  return (
    <section className="card">
      <h1>Page not found</h1>
      <p>
        <Link to="/">Go to the home page</Link>
      </p>
    </section>
  )
}
