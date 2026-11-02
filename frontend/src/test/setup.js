// Runs before every test file (see `test.setupFiles` in vite.config.js).

// Adds DOM matchers such as expect(el).toBeInTheDocument().
import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './server.js'

// 'error': a request without a matching handler fails the test, so a typo in a
// URL can't silently pass.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterEach(() => {
  // Unmount whatever the test rendered so the next test starts from a blank page.
  cleanup()
  server.resetHandlers()
  localStorage.clear()
})

afterAll(() => server.close())
