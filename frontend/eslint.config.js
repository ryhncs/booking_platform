import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

// ESLint "flat config": an array of config objects applied in order.
export default [
  { ignores: ['dist', 'coverage'] },
  js.configs.recommended,
  // Enforces the Rules of Hooks (only call hooks at the top level of a
  // component) and checks useEffect dependency lists.
  reactHooks.configs.flat.recommended,
  // Warns when a file exports non-components, which breaks hot reload.
  reactRefresh.configs.vite,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // Allow intentionally unused args/vars when prefixed with "_".
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    // Config files and tests run in Node, not the browser.
    files: ['*.config.js', 'src/test/**', '**/*.test.{js,jsx}'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
    rules: { 'react-refresh/only-export-components': 'off' },
  },
]
