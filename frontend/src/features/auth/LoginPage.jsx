import { useState } from 'react'
import { useSelector } from 'react-redux'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ErrorMessage } from '../../components/Status.jsx'
import { useLoginMutation } from './authApi.js'
import { selectIsLoggedIn } from './authSlice.js'

export default function LoginPage() {
  // "Controlled inputs": React state is the single source of truth for what
  // the fields contain, so the values are always available when submitting.
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  // A mutation hook returns [trigger, state]. Nothing is sent until we call login().
  const [login, { isLoading, error }] = useLoginMutation()
  const isLoggedIn = useSelector(selectIsLoggedIn)
  const navigate = useNavigate()
  const location = useLocation()

  // Where ProtectedRoute was trying to take the user, or the home page.
  const from = location.state?.from?.pathname ?? '/'

  if (isLoggedIn) return <Navigate to={from} replace />

  async function handleSubmit(event) {
    event.preventDefault() // stop the browser's full-page form submit
    try {
      // unwrap() turns the mutation result into a normal promise that throws
      // on error, which reads naturally with try/catch.
      await login({ email, password }).unwrap()
      navigate(from, { replace: true })
    } catch {
      // `error` from the hook is now set and rendered below.
    }
  }

  return (
    <section className="auth-card card">
      <h1>Log in</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <ErrorMessage error={error}>
            {error.status === 401 ? 'Wrong email or password.' : undefined}
          </ErrorMessage>
        )}
        <button type="submit" className="btn btn-primary" disabled={isLoading}>
          {isLoading ? 'Logging in…' : 'Log in'}
        </button>
      </form>
      <p className="muted">
        No account yet? <Link to="/register">Create one</Link>
      </p>
    </section>
  )
}
