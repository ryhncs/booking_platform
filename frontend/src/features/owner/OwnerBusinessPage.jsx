import { Link, useParams } from 'react-router-dom'

import { ErrorMessage, Loading } from '../../components/Status.jsx'
import { useCurrentUser } from '../auth/useCurrentUser.js'
import { useGetBusinessQuery } from '../businesses/businessesApi.js'
import BusinessForm from './BusinessForm.jsx'
import { useUpdateBusinessMutation } from './ownerApi.js'
import ServicesSection from './ServicesSection.jsx'
import StaffSection from './StaffSection.jsx'

export default function OwnerBusinessPage() {
  const businessId = Number(useParams().businessId)
  const { user } = useCurrentUser()
  const business = useGetBusinessQuery(businessId)
  const [updateBusiness, update] = useUpdateBusinessMutation()

  if (business.isLoading) return <Loading label="Loading business…" />
  if (business.error) return <ErrorMessage error={business.error} onRetry={business.refetch} />
  // Anyone can *read* a business, so check ownership before showing edit
  // controls. (The API would reject the writes anyway.)
  if (business.data.owner !== user.id) {
    return <ErrorMessage>You can only manage your own businesses.</ErrorMessage>
  }

  return (
    <section>
      <p>
        <Link to="/owner/businesses">← My businesses</Link>
      </p>
      <div className="page-header">
        <h1>{business.data.name}</h1>
        <Link to={`/businesses/${businessId}`}>See it as a customer</Link>
      </div>

      <div className="card">
        <h2>Details</h2>
        {update.isSuccess && (
          <p className="alert alert-success" role="status">
            Saved.
          </p>
        )}
        <BusinessForm
          // A new key re-mounts the form, re-reading `initial` after a save.
          key={business.data.timezone + business.data.name + business.data.slug}
          initial={business.data}
          onSubmit={(values) => updateBusiness({ id: businessId, ...values })}
          submitLabel="Save changes"
          isSaving={update.isLoading}
          error={update.error}
        />
      </div>

      <StaffSection business={business.data} />
      <ServicesSection business={business.data} />
    </section>
  )
}
