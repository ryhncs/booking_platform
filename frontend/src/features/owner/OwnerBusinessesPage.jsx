import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { useListBusinessesQuery } from '../businesses/businessesApi.js'
import BusinessForm from './BusinessForm.jsx'
import { useCreateBusinessMutation } from './ownerApi.js'

export default function OwnerBusinessesPage() {
  // mine=true asks the API for only the businesses this owner owns.
  const { data, isLoading, error, refetch } = useListBusinessesQuery({ mine: true })
  const [createBusiness, creation] = useCreateBusinessMutation()
  const [showForm, setShowForm] = useState(false)
  const navigate = useNavigate()

  async function create(values) {
    try {
      const business = await createBusiness(values).unwrap()
      navigate(`/owner/businesses/${business.id}`)
    } catch {
      // field errors are shown by the form
    }
  }

  const hasNone = data && data.results.length === 0

  return (
    <section>
      <div className="page-header">
        <h1>My businesses</h1>
        {!showForm && !hasNone && (
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            New business
          </button>
        )}
      </div>

      {(showForm || hasNone) && (
        <div className="card">
          <h2>{hasNone ? 'Set up your first business' : 'New business'}</h2>
          <BusinessForm
            onSubmit={create}
            submitLabel="Create business"
            isSaving={creation.isLoading}
            error={creation.error}
          />
        </div>
      )}

      {isLoading ? (
        <Loading label="Loading your businesses…" />
      ) : error ? (
        <ErrorMessage error={error} onRetry={refetch} />
      ) : hasNone ? (
        <Empty>You don't have a business yet. Create one above to start taking bookings.</Empty>
      ) : (
        <ul className="grid list-plain">
          {data.results.map((business) => (
            <li key={business.id} className="card">
              <h2>{business.name}</h2>
              <p className="muted">{business.timezone}</p>
              <div className="actions">
                <Link className="btn btn-primary" to={`/owner/businesses/${business.id}`}>
                  Manage
                </Link>
                <Link className="btn" to="/owner/bookings">
                  Bookings
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
