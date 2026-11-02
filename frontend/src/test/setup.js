// Runs before every test file (see `test.setupFiles` in vite.config.js).

// Adds DOM matchers such as expect(el).toBeInTheDocument().
import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './server.js'

// findBy*/waitFor give up after 1s by default. Test files run in parallel, and
// a cold first render on a busy CI machine can take longer than that, which
// makes tests flaky. Passing tests still finish as soon as the UI is ready;
// this only changes how long a failing one waits.
configure({ asyncUtilTimeout: 3000 })

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
