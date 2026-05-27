import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Upload, ClipboardList, FileCheck, Info } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import ReviewQueue from './pages/ReviewQueue'

export default function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-logo">
            <h1>🌱 Breathe ESG</h1>
            <span>Data Review Platform</span>
          </div>
          <nav className="sidebar-nav">
            <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <LayoutDashboard size={16} /> Dashboard
            </NavLink>
            <NavLink to="/upload" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Upload size={16} /> Upload Data
            </NavLink>
            <NavLink to="/review" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <ClipboardList size={16} /> Review Queue
            </NavLink>
          </nav>
          <div style={{ padding: '16px 20px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: 11, color: '#6b7280' }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#9ca3af' }}>Sources</div>
              <div>SAP · Utility · Travel</div>
              <div style={{ marginTop: 8, fontWeight: 500, color: '#9ca3af' }}>AI</div>
              <div>Gemini · LangGraph</div>
            </div>
          </div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/review" element={<ReviewQueue />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
