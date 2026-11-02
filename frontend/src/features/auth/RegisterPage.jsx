import { useState } from 'react'
import { useSelector } from 'react-redux'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { ErrorMessage } from '../../components/Status.jsx'
import { fieldErrors } from '../../utils/errors.js'
import { useLoginMutation, useRegisterMutation } from './authApi.js'
import { selectIsLoggedIn } from './authSlice.js'

const EMPTY = { email: '', password: '', first_name: '', last_name: '', role: 'customer' }

export default function RegisterPage() {
  // One state object for the whole form; `update` changes a single field.
  const [form, setForm] = useState(EMPTY)
  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const [register, registerState] = useRegisterMutation()
  const [login, loginState] = useLoginMutation()
  const isLoggedIn = useSelector(selectIsLoggedIn)
  const navigate = useNavigate()

  if (isLoggedIn) return <Navigate to="/" replace />

  const error = registerState.error ?? loginState.error
  const fields = fieldErrors(registerState.error)
  const busy = registerState.isLoading || loginState.isLoading

  async function handleSubmit(event) {
    event.preventDefault()
    try {
      await register(form).unwrap()
      // Registration doesn't return tokens, so log straight in with the same
      // credentials: one less step for the user.
      await login({ email: form.email, password: form.password }).unwrap()
      navigate(form.role === 'owner' ? '/owner/businesses' : '/', { replace: true })
    } catch {
      // Errors are rendered from the hook state.
    }
  }

  return (
    <section className="auth-card card">
      <h1>Create an account</h1>
      <form onSubmit={handleSubmit} className="form" noValidate>
        <fieldset className="role-choice">
          <legend>I want to</legend>
          <label>
            <input
              type="radio"
              name="role"
              value="customer"
              checked={form.role === 'customer'}
              onChange={update('role')}
            />
            Book appointments
          </label>
          <label>
            <input
              type="radio"
              name="role"
              value="owner"
              checked={form.role === 'owner'}
              onChange={update('role')}
            />
            Run a business
          </label>
        </fieldset>
        <div className="form-row">
          <label>
            First name
            <input value={form.first_name} onChange={update('first_name')} autoComplete="given-name" />
          </label>
          <label>
            Last name
            <input value={form.last_name} onChange={update('last_name')} autoComplete="family-name" />
          </label>
        </div>
        <label>
          Email
          <input
            type="email"
            required
            autoComplete="email"
            value={form.email}
            onChange={update('email')}
            aria-invalid={Boolean(fields.email)}
          />
          {fields.email && <span className="field-error">{fields.email}</span>}
        </label>
        <label>
          Password
          <input
            type="password"
            required
            autoComplete="new-password"
            value={form.password}
            onChange={update('password')}
            aria-invalid={Boolean(fields.password)}
          />
          {fields.password && <span className="field-error">{fields.password}</span>}
        </label>
        {/* Field errors are shown inline above; only show the banner for other errors. */}
        {error && !fields.email && !fields.password && <ErrorMessage error={error} />}
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="muted">
        Already registered? <Link to="/login">Log in</Link>
      </p>
    </section>
  )
}
