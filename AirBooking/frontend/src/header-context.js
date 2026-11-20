export function headerSection(pathname) {
  pathname = pathname.replace(/\/+$/, '')
  if (pathname === '/admin') return { label: 'Administration', icon: 'admin' }
  if (pathname === '/flight-status') return { label: 'Flight status', icon: 'status' }
  if (pathname === '/trips') return { label: 'My trips', icon: 'trips' }
  if (pathname === '/complaints') return { label: 'Traveler support', icon: 'support' }
  if (/^\/flights\/[^/]+\/payment$/.test(pathname)) return { label: 'Checkout', icon: 'flights' }
  if (/^\/flights\/[^/]+$/.test(pathname)) return { label: 'Flight details', icon: 'flights' }
  return { label: 'Explore flights', icon: 'flights' }
}
