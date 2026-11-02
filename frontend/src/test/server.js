import { setupServer } from 'msw/node'

// Mock Service Worker intercepts fetch() in tests and answers with the
// handlers each test registers via server.use(...). Nothing reaches a real
// server, and an unexpected request fails the test (see setup.js).
export const server = setupServer()

// Paths like "*/api/me/" match on any origin, so tests don't care what
// window.location.origin happens to be under jsdom.
export const api = (path) => `*/api${path}`
