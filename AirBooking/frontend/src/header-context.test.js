import assert from 'node:assert/strict'
import test from 'node:test'
import { headerSection } from './header-context.js'

test('header context follows the current workspace route', () => {
  const sections = {
    '/admin': 'Administration', '/flight-status': 'Flight status', '/trips': 'My trips',
    '/complaints': 'Traveler support', '/flights': 'Explore flights',
    '/flights/12': 'Flight details', '/flights/12/payment': 'Checkout',
  }
  for (const [pathname, label] of Object.entries(sections)) {
    assert.equal(headerSection(pathname).label, label)
    assert.equal(headerSection(pathname + '/').label, label)
    assert.ok(['admin', 'status', 'trips', 'support', 'flights'].includes(headerSection(pathname).icon))
  }
})
