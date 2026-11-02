import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import App from './App.jsx'

test('the real App boots and sends a logged-out visitor to the login page', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
})
