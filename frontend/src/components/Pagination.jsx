/**
 * Prev/next controls for a DRF paginated response ({ count, next, previous }).
 * The page number lives in the parent's state; this only reports changes.
 */
export default function Pagination({ data, page, onPageChange, isFetching }) {
  if (!data || (!data.next && !data.previous)) return null
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="btn btn-small"
        disabled={!data.previous || isFetching}
        onClick={() => onPageChange(page - 1)}
      >
        Previous
      </button>
      <span className="muted">Page {page}</span>
      <button
        type="button"
        className="btn btn-small"
        disabled={!data.next || isFetching}
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </button>
    </nav>
  )
}
