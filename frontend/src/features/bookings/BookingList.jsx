import { useState } from 'react'

import Pagination from '../../components/Pagination.jsx'
import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { useCurrentUser } from '../auth/useCurrentUser.js'
import BookingCard from './BookingCard.jsx'
import { useListBookingsQuery } from './bookingsApi.js'

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'cancelled', label: 'Cancelled' },
]

/**
 * A filterable, paginated list of bookings. `scope` picks which ones:
 * "mine" (bookings I made) or "business" (bookings at businesses I own).
 */
export default function BookingList({ scope, viewer, empty }) {
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const { user } = useCurrentUser()
  const { data, isLoading, isFetching, error, refetch } = useListBookingsQuery({ scope, status, page })

  return (
    <>
      <div className="actions" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            className={`btn btn-small${status === f.value ? ' btn-primary' : ''}`}
            aria-pressed={status === f.value}
            onClick={() => {
              setStatus(f.value)
              setPage(1) // a different filter starts from the first page
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Loading label="Loading bookings…" />
      ) : error ? (
        <ErrorMessage error={error} onRetry={refetch} />
      ) : data.results.length === 0 ? (
        <Empty>{status ? `No ${status} bookings.` : empty}</Empty>
      ) : (
        <>
          <ul className="list-plain" style={{ opacity: isFetching ? 0.6 : 1 }}>
            {data.results.map((booking) => (
              <BookingCard key={booking.id} booking={booking} viewer={viewer} currentUserId={user?.id} />
            ))}
          </ul>
          <Pagination data={data} page={page} onPageChange={setPage} isFetching={isFetching} />
        </>
      )}
    </>
  )
}
