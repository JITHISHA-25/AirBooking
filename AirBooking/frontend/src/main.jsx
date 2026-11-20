import { StrictMode, useEffect, useState, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { BriefcaseBusiness, ChevronRight, LogOut, Menu, MessageSquare, Plane, Radio, ShieldCheck, X } from 'lucide-react'
import { getSession, signOut, subscribe } from './api'
import { Logo } from './ui'
import { AuthPage, FlightPage, SearchPage, TripsPage } from './traveler'
import { AdminPage } from './admin'
import { ComplaintsPage } from './complaints'
import { PaymentPage } from './payment'
import { FlightStatusPage } from './flight-status'
import { headerSection } from './header-context'
import './style.css'

function Gate({ admin = false }) {
  const session = useSyncExternalStore(subscribe, getSession)
  if (!session) return <Navigate to="/login" replace />
  if (admin && !session.user.is_staff) return <Navigate to="/flights" replace />
  return <Outlet />
}

function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const session = useSyncExternalStore(subscribe, getSession)
  const [menuOpen, setMenuOpen] = useState(false)
  useEffect(() => {
    if (!menuOpen) return
    function closeOnEscape(event) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        document.getElementById('navigation-toggle')?.focus()
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [menuOpen])
  if (!session) return null
  const { user } = session
  const displayName = user.first_name || user.username
  const section = headerSection(location.pathname)
  const SectionIcon = { flights: Plane, status: Radio, trips: BriefcaseBusiness, support: MessageSquare, admin: ShieldCheck }[section.icon]
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header"><div className="nav">
      <div className="header-brand">
        <button id="navigation-toggle" type="button" className="icon-button navigation-toggle"
          aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen}
          aria-controls="side-navigation" onClick={() => setMenuOpen(open => !open)}>
          {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>
        <div className="header-brand-lockup"><Logo /><span className="header-tagline">Your journey, simplified.</span></div>
      </div>
      <div className="header-toolbar">
        <div className="header-context"><span className="header-section-icon"><SectionIcon size={19} aria-hidden="true" /></span>
          <div><span className="header-context-label">{user.is_staff ? 'Management workspace' : 'Your travel workspace'}</span>
            <nav className="header-breadcrumb" aria-label="Breadcrumb"><Link to="/">Home</Link><ChevronRight size={13} aria-hidden="true" /><span aria-current="page">{section.label}</span></nav>
          </div>
        </div>
        <div className="header-actions">
          <Link className="header-quick-link" to="/flight-status"><Radio size={16} aria-hidden="true" /> Flight status</Link>
          <div className="account">
            <span className="account-avatar" aria-hidden="true">{displayName.slice(0, 1).toUpperCase()}</span>
            <div className="account-details"><span title={displayName}>{displayName}</span><small>{user.is_staff ? 'Administrator' : 'Traveler'}</small></div>
            <span className="account-divider" aria-hidden="true" />
            <button type="button" className="icon-button header-sign-out" aria-label="Sign out" title="Sign out"
              onClick={() => { signOut(); navigate('/login', { replace: true }) }}><LogOut size={18} aria-hidden="true" /></button>
          </div>
        </div>
      </div>
    </div></header>
    {menuOpen && <button type="button" className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <aside id="side-navigation" className={'sidebar' + (menuOpen ? ' is-open' : '')}>
      <p className="sidebar-label">Travel workspace</p>
      <nav className="nav-links" aria-label="Main navigation">
        <NavLink to="/flights" onClick={() => setMenuOpen(false)}><Plane size={19} aria-hidden="true" /> Flights</NavLink>
        <NavLink to="/flight-status" onClick={() => setMenuOpen(false)}><Radio size={19} aria-hidden="true" /> Flight Status</NavLink>
        <NavLink to="/trips" onClick={() => setMenuOpen(false)}><BriefcaseBusiness size={19} aria-hidden="true" /> My Trips</NavLink>
        <NavLink to="/complaints" onClick={() => setMenuOpen(false)}><MessageSquare size={19} aria-hidden="true" /> Complaints</NavLink>
        {user.is_staff && <NavLink to="/admin" onClick={() => setMenuOpen(false)}><ShieldCheck size={19} aria-hidden="true" /> Admin</NavLink>}
      </nav>
      <div className="sidebar-note"><span className="sidebar-note-icon"><Plane size={21} aria-hidden="true" /></span>
        <strong>A little less planning.<br />A little more going.</strong>
        <p>Flights, meals, and trip updates. All in one place.</p>
        <Link to="/trips" onClick={() => setMenuOpen(false)}>View my trips <span aria-hidden="true">↗</span></Link>
      </div>
    </aside>
    <div className="app-content">
      <main id="main-content" className="shell page" tabIndex={-1}><Outlet /></main>
      <footer className="shell footer"><span>AirBooking <span className="footer-separator" aria-hidden="true">/</span> Your journey, simplified.</span><span>{location.pathname.startsWith('/flight-status') ? 'Flight times shown in airport local time' : 'Flight times · IST (Asia/Kolkata)'}</span></footer>
    </div>
  </>
}

function Home() {
  const session = useSyncExternalStore(subscribe, getSession)
  return <Navigate to={session?.user.is_staff ? '/admin' : '/flights'} replace />
}

function App() {
  return <BrowserRouter><Routes>
    <Route path="/" element={<Home />} />
    <Route path="/login" element={<AuthPage key="login" />} />
    <Route path="/register" element={<AuthPage key="register" registration />} />
    <Route element={<Gate />}>
      <Route element={<Layout />}>
        <Route path="/flights" element={<SearchPage />} />
        <Route path="/flight-status" element={<FlightStatusPage />} />
        <Route path="/flights/:id" element={<FlightPage />} />
        <Route path="/flights/:id/payment" element={<PaymentPage />} />
        <Route path="/trips" element={<TripsPage />} />
        <Route path="/complaints" element={<ComplaintsPage />} />
        <Route element={<Gate admin />}><Route path="/admin" element={<AdminPage />} /></Route>
      </Route>
    </Route>
    <Route path="*" element={<main className="shell page"><h1>Page not found</h1><Link to="/">Back to AirBooking</Link></main>} />
  </Routes></BrowserRouter>
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
