// RTK Query hands components an `error` object instead of throwing. Its shape:
//   { status: 400, data: { detail: '...', code: 'slot_unavailable' } }  server answered
//   { status: 400, data: { email: ['already exists'] } }                 field errors (DRF)
//   { status: 'FETCH_ERROR', error: '...' }                             no response at all
// These helpers turn that into something to show a person.

/** The machine-readable code our API puts on booking errors, if any. */
export function errorCode(error) {
  return error?.data?.code ?? null
}

/** Per-field messages from a DRF validation error: { email: 'already exists' }. */
export function fieldErrors(error) {
  const data = error?.data
  if (!data || typeof data !== 'object' || Array.isArray(data)) return {}
  const fields = {}
  for (const [field, messages] of Object.entries(data)) {
    if (field === 'detail' || field === 'code') continue
    fields[field] = Array.isArray(messages) ? messages.join(' ') : String(messages)
  }
  return fields
}

/** One human-readable sentence for any API error. */
export function errorMessage(error) {
  if (!error) return ''
  if (error.status === 'FETCH_ERROR') return "Can't reach the server. Check your connection and try again."
  if (error.status === 'PARSING_ERROR' || error.status >= 500) {
    return 'Something went wrong on our side. Please try again.'
  }
  const data = error.data
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data)) return data.join(' ')
  // DRF puts non-field errors under "non_field_errors"; field errors are
  // usually shown next to their inputs, so summarise them here.
  const fields = fieldErrors(error)
  if (fields.non_field_errors) return fields.non_field_errors
  const entries = Object.entries(fields)
  if (entries.length) return entries.map(([field, msg]) => `${field}: ${msg}`).join(' ')
  return 'The request failed. Please try again.'
}
