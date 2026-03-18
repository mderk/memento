# Jest/Vitest Platform Rules

## Frontend Testing (React/Vue + Jest/Vitest)

- Prefer user-centric queries (`getByRole`, `getByText`, `getByLabelText`)
- `userEvent` over `fireEvent` for realistic interaction
- `findBy*` / `waitFor` for async UI state (no fixed timeouts)
- Network calls mocked (MSW preferred); no real HTTP
- Avoid brittle UI selectors; prefer role/label/text, `data-testid` as last resort
- `act()` warnings indicate missing async handling — fix, don't suppress

## Node.js Backend Testing

- Use `describe`/`it` blocks with clear test names
- Mock external dependencies at module boundaries
- Async tests use `async/await`; no unhandled promise rejections
- DB state isolated per test (transactions or fresh seeds)

## E2E (Playwright)

- No `page.waitForTimeout`; use locator assertions with auto-wait
- Stable selectors + explicit assertions on state transitions
- Minimal E2E scope; don't duplicate unit/integration coverage

## E2E (Cypress)

- No `cy.wait(ms)`; use `cy.intercept()` + route aliases
- Stable selectors (`data-cy` attributes); avoid CSS class selectors
- Minimal E2E scope; don't duplicate unit/integration coverage
