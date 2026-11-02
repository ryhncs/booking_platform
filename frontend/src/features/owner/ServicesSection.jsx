import { useState } from 'react'

import { Empty, ErrorMessage, Loading } from '../../components/Status.jsx'
import { errorMessage, fieldErrors } from '../../utils/errors.js'
import { useListServicesQuery, useListStaffQuery } from '../businesses/businessesApi.js'
import { useCreateServiceMutation, useDeleteServiceMutation, useUpdateServiceMutation } from './ownerApi.js'

export default function ServicesSection({ business }) {
  const services = useListServicesQuery({ business: business.id })
  const staff = useListStaffQuery({ business: business.id })
  const [createService, creation] = useCreateServiceMutation()
  const [adding, setAdding] = useState(false)

  const staffList = staff.data?.results ?? []

  async function create(values) {
    try {
      await createService({ business: business.id, ...values }).unwrap()
      setAdding(false)
    } catch {
      // shown by the form
    }
  }

  return (
    <div className="card">
      <div className="row">
        <h2>Services</h2>
        {!adding && (
          <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
            Add service
          </button>
        )}
      </div>

      {adding && (
        <ServiceForm
          staffList={staffList}
          onSubmit={create}
          onCancel={() => setAdding(false)}
          submitLabel="Create service"
          state={creation}
        />
      )}

      {services.isLoading ? (
        <Loading />
      ) : services.error ? (
        <ErrorMessage error={services.error} onRetry={services.refetch} />
      ) : services.data.results.length === 0 ? (
        <Empty>No services yet. Add one so customers have something to book.</Empty>
      ) : (
        <ul className="list">
          {services.data.results.map((service) => (
            <ServiceRow key={service.id} service={service} staffList={staffList} />
          ))}
        </ul>
      )}
    </div>
  )
}

function ServiceRow({ service, staffList }) {
  const [updateService, update] = useUpdateServiceMutation()
  const [deleteService, deletion] = useDeleteServiceMutation()
  const [editing, setEditing] = useState(false)
  const names = new Map(staffList.map((s) => [s.id, s.display_name]))

  async function save(values) {
    try {
      await updateService({ id: service.id, ...values }).unwrap()
      setEditing(false)
    } catch {
      // shown by the form
    }
  }

  if (editing) {
    return (
      <li>
        <ServiceForm
          initial={service}
          staffList={staffList}
          onSubmit={save}
          onCancel={() => setEditing(false)}
          submitLabel="Save"
          state={update}
        />
      </li>
    )
  }

  return (
    <li>
      <div className="row">
        <div>
          <strong>{service.name}</strong> {!service.is_active && <span className="badge">inactive</span>}
          <div className="muted">
            {service.duration_minutes} min · {Number(service.price).toLocaleString()} ·{' '}
            {service.staff.length ? service.staff.map((id) => names.get(id) ?? '…').join(', ') : 'nobody offers it yet'}
          </div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-small" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button
            type="button"
            className="btn btn-small btn-danger"
            disabled={deletion.isLoading}
            onClick={() => window.confirm(`Delete ${service.name}?`) && deleteService(service.id)}
          >
            Delete
          </button>
        </div>
      </div>
      {deletion.error && (
        <ErrorMessage>
          {deletion.error.status === 409
            ? 'This service has bookings, so it can\'t be deleted. Edit it and untick "Active" instead.'
            : errorMessage(deletion.error)}
        </ErrorMessage>
      )}
    </li>
  )
}

function ServiceForm({ initial, staffList, onSubmit, onCancel, submitLabel, state }) {
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    duration_minutes: initial?.duration_minutes ?? 60,
    price: initial?.price ?? '',
    staff: initial?.staff ?? [],
    is_active: initial?.is_active ?? true,
  })
  const fields = fieldErrors(state.error)

  function toggleStaff(id) {
    // Never mutate state in place; build a new array so React sees a change.
    setForm({
      ...form,
      staff: form.staff.includes(id) ? form.staff.filter((s) => s !== id) : [...form.staff, id],
    })
  }

  function handleSubmit(event) {
    event.preventDefault()
    onSubmit({ ...form, duration_minutes: Number(form.duration_minutes) })
  }

  return (
    <form className="form card" onSubmit={handleSubmit}>
      <div className="form-row">
        <label>
          Name
          <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          {fields.name && <span className="field-error">{fields.name}</span>}
        </label>
        <label>
          Duration (minutes)
          <input
            type="number"
            min={5}
            max={480}
            step={5}
            required
            value={form.duration_minutes}
            onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
          />
          {fields.duration_minutes && <span className="field-error">{fields.duration_minutes}</span>}
        </label>
        <label>
          Price
          <input
            type="number"
            min={0}
            step="0.01"
            required
            value={form.price}
            onChange={(e) => setForm({ ...form, price: e.target.value })}
          />
          {fields.price && <span className="field-error">{fields.price}</span>}
        </label>
      </div>
      <fieldset>
        <legend>Offered by</legend>
        {staffList.length === 0 ? (
          <span className="muted">Add staff first, then choose who offers this service.</span>
        ) : (
          <div className="checkbox-list">
            {staffList.map((member) => (
              <label key={member.id}>
                <input type="checkbox" checked={form.staff.includes(member.id)} onChange={() => toggleStaff(member.id)} />
                {member.display_name}
              </label>
            ))}
          </div>
        )}
        {fields.staff && <span className="field-error">{fields.staff}</span>}
      </fieldset>
      <label className="checkbox-list">
        <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
        Active (customers can book it)
      </label>
      {state.error && !Object.keys(fields).length && <ErrorMessage error={state.error} />}
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={state.isLoading}>
          {state.isLoading ? 'Saving…' : submitLabel}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
