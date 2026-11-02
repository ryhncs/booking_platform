// Runs before every test file (see `test.setupFiles` in vite.config.js).

// Adds DOM matchers such as expect(el).toBeInTheDocument().
import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  // Unmount whatever the test rendered so the next test starts from a blank page.
  cleanup()
  localStorage.clear()
})
