import { useState } from 'react'

import { ErrorMessage, Loading } from '../../components/Status.jsx'
import { fieldErrors } from '../../utils/errors.js'
import { useListTimezonesQuery } from '../businesses/businessesApi.js'
import { defaultTimezone, slugify } from './formHelpers.js'

/**
 * Create or edit a business. `initial` is the existing business when editing.
 *
 * The form copies `initial` into local state once, when it mounts. To load a
 * different business, the parent re-mounts it with a new `key` instead of
 * syncing props into state with an effect (simpler, and no stale-state bugs).
 */
export default function BusinessForm({ initial, onSubmit, submitLabel, isSaving, error }) {
  const timezones = useListTimezonesQuery()
  const [name, setName] = useState(initial?.name ?? '')
  const [slug, setSlug] = useState(initial?.slug ?? '')
  // While creating, keep the slug in step with the name until the owner edits it.
  const [slugTouched, setSlugTouched] = useState(Boolean(initial))
  const [timezone, setTimezone] = useState(initial?.timezone ?? null)
  const fields = fieldErrors(error)

  if (timezones.isLoading) return <Loading label="Loading timezones…" />
  if (timezones.error) return <ErrorMessage error={timezones.error} onRetry={timezones.refetch} />

  // Until the owner picks one, suggest their own zone.
  const chosenZone = timezone ?? defaultTimezone(timezones.data)

  function handleSubmit(event) {
    event.preventDefault()
    onSubmit({ name, slug, timezone: chosenZone })
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="form-row">
        <label>
          Name
          <input
            required
            value={name}
            aria-invalid={Boolean(fields.name)}
            onChange={(e) => {
              setName(e.target.value)
              if (!slugTouched) setSlug(slugify(e.target.value))
            }}
          />
          {fields.name && <span className="field-error">{fields.name}</span>}
        </label>
        <label>
          Web address (slug)
          <input
            required
            value={slug}
            pattern="[-a-zA-Z0-9_]+"
            aria-invalid={Boolean(fields.slug)}
            onChange={(e) => {
              setSlugTouched(true)
              setSlug(e.target.value)
            }}
          />
          {fields.slug && <span className="field-error">{fields.slug}</span>}
        </label>
      </div>
      <label>
        Timezone (working hours are entered in this zone)
        <select value={chosenZone} onChange={(e) => setTimezone(e.target.value)} aria-invalid={Boolean(fields.timezone)}>
          {timezones.data.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
        {fields.timezone && <span className="field-error">{fields.timezone}</span>}
      </label>
      {error && !Object.keys(fields).length && <ErrorMessage error={error} />}
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={isSaving}>
          {isSaving ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}
