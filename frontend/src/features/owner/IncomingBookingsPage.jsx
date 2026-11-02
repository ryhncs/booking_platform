import { Link } from 'react-router-dom'

import BookingList from '../bookings/BookingList.jsx'

/**
 * Bookings made at the businesses this owner runs. Same list and cards as
 * "My bookings"; only the scope and wording differ, which is why both pages
 * are thin wrappers around BookingList.
 */
export default function IncomingBookingsPage() {
  return (
    <section>
      <div className="page-header">
        <h1>Incoming bookings</h1>
        <Link to="/owner/businesses">Manage businesses</Link>
      </div>
      <p className="muted">
        Pending bookings are held for 10 minutes. You or the customer can confirm them; either of you
        can cancel, and the other side is emailed who cancelled and why.
      </p>
      <BookingList scope="business" viewer="owner" empty="No bookings at your businesses yet." />
    </section>
  )
}
