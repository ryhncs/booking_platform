import { useState } from 'react'

import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { errorMessage } from '../../utils/errors.js'
import { useListStaffQuery } from '../businesses/businessesApi.js'
import { useCreateStaffMutation, useDeleteStaffMutation, useUpdateStaffMutation } from './ownerApi.js'
import WorkingHoursEditor from './WorkingHoursEditor.jsx'

export default function StaffSection({ business }) {
  const staff = useListStaffQuery({ business: business.id })
  const [createStaff, creation] = useCreateStaffMutation()
  const [name, setName] = useState('')

  async function add(event) {
    event.preventDefault()
    try {
      await createStaff({ business: business.id, display_name: name }).unwrap()
      setName('')
    } catch {
      // shown below
    }
  }

  return (
    <div className="card">
      <h2>Staff</h2>
      {staff.isLoading ? (
        <Loading />
      ) : staff.error ? (
        <ErrorMessage error={staff.error} onRetry={staff.refetch} />
      ) : staff.data.results.length === 0 ? (
        <Empty>Add the people who take appointments.</Empty>
      ) : (
        <ul className="list">
          {staff.data.results.map((member) => (
            <StaffRow key={member.id} member={member} timeZone={business.timezone} />
          ))}
        </ul>
      )}

      <form className="form-row" onSubmit={add}>
        <label>
          New staff member
          <input required placeholder="Display name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="actions" style={{ alignItems: 'end' }}>
          <button type="submit" className="btn btn-primary" disabled={creation.isLoading}>
            Add staff member
          </button>
        </div>
      </form>
      {creation.error && <ErrorMessage error={creation.error} />}
    </div>
  )
}

function StaffRow({ member, timeZone }) {
  const [updateStaff, update] = useUpdateStaffMutation()
  const [deleteStaff, deletion] = useDeleteStaffMutation()
  const [showHours, setShowHours] = useState(false)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(member.display_name)
  const error = update.error ?? deletion.error

  async function rename(event) {
    event.preventDefault()
    try {
      await updateStaff({ id: member.id, display_name: name }).unwrap()
      setEditing(false)
    } catch {
      // shown below
    }
  }

  return (
    <li>
      <div className="row">
        {editing ? (
          <form className="actions" onSubmit={rename}>
            <input aria-label="Display name" required value={name} onChange={(e) => setName(e.target.value)} />
            <button type="submit" className="btn btn-small btn-primary" disabled={update.isLoading}>
              Save
            </button>
            <button type="button" className="btn btn-small" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <strong>
            {member.display_name} {!member.is_active && <span className="badge">inactive</span>}
          </strong>
        )}
        <div className="actions">
          <button type="button" className="btn btn-small" onClick={() => setShowHours(!showHours)} aria-expanded={showHours}>
            {showHours ? 'Hide hours' : 'Hours'}
          </button>
          {!editing && (
            <button type="button" className="btn btn-small" onClick={() => setEditing(true)}>
              Rename
            </button>
          )}
          <button
            type="button"
            className="btn btn-small"
            disabled={update.isLoading}
            onClick={() => updateStaff({ id: member.id, is_active: !member.is_active })}
          >
            {member.is_active ? 'Deactivate' : 'Activate'}
          </button>
          <button
            type="button"
            className="btn btn-small btn-danger"
            disabled={deletion.isLoading}
            onClick={() => {
              // window.confirm is crude but honest: deleting can't be undone.
              if (window.confirm(`Remove ${member.display_name}?`)) deleteStaff(member.id)
            }}
          >
            Delete
          </button>
        </div>
      </div>
      {error && (
        <ErrorMessage>
          {/* The API refuses (409) to delete someone who still has bookings. */}
          {error.status === 409
            ? `${member.display_name} still has bookings, so they can't be deleted. Deactivate them instead to stop new bookings.`
            : errorMessage(error)}
        </ErrorMessage>
      )}
      {showHours && <WorkingHoursEditor staff={member} timeZone={timeZone} />}
    </li>
  )
}
