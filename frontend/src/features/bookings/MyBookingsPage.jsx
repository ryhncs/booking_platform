import { Link, useLocation } from 'react-router-dom'

import BookingList from './BookingList.jsx'

export default function MyBookingsPage() {
  // Set by BookingPage after a successful booking (navigation state).
  const justBooked = useLocation().state?.justBooked

  return (
    <section>
      <div className="page-header">
        <h1>My bookings</h1>
        <Link to="/businesses">Book something new</Link>
      </div>

      {justBooked && (
        <p className="alert alert-success" role="status">
          Booked! Confirm it below within 10 minutes to keep the slot.
        </p>
      )}

      <BookingList
        scope="mine"
        viewer="customer"
        empty={
          <>
            No bookings yet. <Link to="/businesses">Find a business</Link> to book your first appointment.
          </>
        }
      />
    </section>
  )
}
