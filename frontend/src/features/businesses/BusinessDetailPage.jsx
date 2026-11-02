import { Link, useParams } from 'react-router-dom'

import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { useGetBusinessQuery, useListServicesQuery, useListStaffQuery } from './businessesApi.js'

export default function BusinessDetailPage() {
  // URL params are always strings; the API wants numbers in query strings
  // either way, but comparisons with ids from JSON need Number().
  const businessId = Number(useParams().businessId)

  // Three independent queries run in parallel; each has its own state.
  const business = useGetBusinessQuery(businessId)
  const services = useListServicesQuery({ business: businessId })
  const staff = useListStaffQuery({ business: businessId })

  if (business.isLoading) return <Loading label="Loading business…" />
  if (business.error) {
    return business.error.status === 404 ? (
      <ErrorMessage>That business doesn't exist (or was removed).</ErrorMessage>
    ) : (
      <ErrorMessage error={business.error} onRetry={business.refetch} />
    )
  }

  // id -> name, to show who offers each service.
  const staffNames = new Map((staff.data?.results ?? []).map((s) => [s.id, s.display_name]))

  return (
    <section>
      <div className="page-header">
        <h1>{business.data.name}</h1>
        <span className="muted">Times are in {business.data.timezone}</span>
      </div>

      <div className="card">
        <h2>Services</h2>
        {services.isLoading ? (
          <Loading />
        ) : services.error ? (
          <ErrorMessage error={services.error} onRetry={services.refetch} />
        ) : services.data.results.length === 0 ? (
          <Empty>This business hasn't added any services yet.</Empty>
        ) : (
          <ul className="list">
            {services.data.results.map((service) => (
              <li key={service.id} className="row">
                <div>
                  <strong>{service.name}</strong>
                  <div className="muted">
                    {service.duration_minutes} min · {Number(service.price).toLocaleString()}
                    {service.staff.length > 0 &&
                      ` · with ${service.staff.map((id) => staffNames.get(id) ?? '…').join(', ')}`}
                  </div>
                </div>
                {service.staff.length > 0 ? (
                  <Link
                    className="btn btn-primary"
                    to={`/businesses/${businessId}/book?service=${service.id}`}
                  >
                    Book
                  </Link>
                ) : (
                  <span className="muted">Not bookable yet</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h2>Staff</h2>
        {staff.isLoading ? (
          <Loading />
        ) : staff.error ? (
          <ErrorMessage error={staff.error} onRetry={staff.refetch} />
        ) : staff.data.results.length === 0 ? (
          <Empty>No staff listed yet.</Empty>
        ) : (
          <ul className="list">
            {staff.data.results.map((member) => (
              <li key={member.id} className="row">
                <strong>{member.display_name}</strong>
                <Link to={`/businesses/${businessId}/book?staff=${member.id}`}>
                  Book with {member.display_name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
