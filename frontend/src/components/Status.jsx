import { errorMessage } from '../utils/errors.js'

// Every page that loads data has the same three "not the happy path" states.
// Sharing these keeps them consistent and accessible.

export function Loading({ label = 'Loading…' }) {
  // role="status" makes screen readers announce it without stealing focus.
  return (
    <p className="status" role="status">
      <span className="spinner" aria-hidden="true" /> {label}
    </p>
  )
}

export function ErrorMessage({ error, children, onRetry }) {
  // role="alert" is announced immediately, which is what you want for errors.
  return (
    <div className="alert alert-error" role="alert">
      <span>{children ?? errorMessage(error)}</span>
      {onRetry && (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>
}
