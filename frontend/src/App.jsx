import { useState } from 'react'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router-dom'

import AppRoutes from './AppRoutes.jsx'
import { makeStore } from './app/store.js'

export default function App() {
  // useState with a function creates the store once per App mount, not on
  // every render (a plain `const store = makeStore()` here would rebuild it).
  const [store] = useState(makeStore)

  return (
    // Provider makes the Redux store (and so every RTK Query hook) available
    // to all components below it.
    <Provider store={store}>
      {/* BrowserRouter keeps the UI in sync with the address bar. Tests use
          MemoryRouter instead, so AppRoutes is kept separate from this. */}
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Provider>
  )
}
