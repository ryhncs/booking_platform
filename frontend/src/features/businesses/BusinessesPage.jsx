import { useState } from 'react'
import { Link } from 'react-router-dom'

import Pagination from '../../components/Pagination.jsx'
import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { useListBusinessesQuery } from './businessesApi.js'

export default function BusinessesPage() {
  const [page, setPage] = useState(1)
  // A query hook fetches on mount and whenever its argument changes (here:
  // the page). Results are cached per argument, so going back to page 1 is instant.
  //   isLoading  - first load, nothing to show yet
  //   isFetching - any request in flight, including a refetch with old data on screen
  const { data, isLoading, isFetching, error, refetch } = useListBusinessesQuery({ page })

  return (
    <section>
      <div className="page-header">
        <h1>Businesses</h1>
        {data && <span className="muted">{data.count} total</span>}
      </div>

      {isLoading ? (
        <Loading label="Loading businesses…" />
      ) : error ? (
        <ErrorMessage error={error} onRetry={refetch} />
      ) : data.results.length === 0 ? (
        <Empty>No businesses yet. Check back soon.</Empty>
      ) : (
        <>
          {/* Fade the old page slightly while the next one loads. */}
          <ul className="grid list-plain" style={{ opacity: isFetching ? 0.6 : 1 }}>
            {data.results.map((business) => (
              <li key={business.id} className="card">
                <h2>{business.name}</h2>
                <p className="muted">Times shown in {business.timezone}</p>
                <Link className="btn btn-primary" to={`/businesses/${business.id}`}>
                  View services
                </Link>
              </li>
            ))}
          </ul>
          <Pagination data={data} page={page} onPageChange={setPage} isFetching={isFetching} />
        </>
      )}
    </section>
  )
}
