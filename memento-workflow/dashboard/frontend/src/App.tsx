import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { fetchInfo, requestShutdown } from './api'
import RunList from './pages/RunList'
import RunDetail from './pages/RunDetail'
import RunDiff from './pages/RunDiff'
import './app.css'

export default function App() {
  const [project, setProject] = useState('')
  const [cwd, setCwd] = useState('')

  useEffect(() => {
    fetchInfo().then((info) => {
      setProject(info.project)
      setCwd(info.cwd)
      document.title = `${info.project} — workflow dashboard`
    }).catch(() => {})

    // No auto-shutdown on navigation events — too unreliable.
    // Server shuts down only via explicit close button (handleClose above).
    // Cancel any pending shutdown from a previous session.
    navigator.sendBeacon('/api/cancel-shutdown')

    return () => {}
  }, [])

  const handleClose = () => {
    requestShutdown()
    // Replace page content — window.close() only works for windows
    // opened via window.open(), not for tabs opened by the OS.
    document.title = 'Dashboard closed'
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:monospace;color:#888;font-size:1.1rem">Dashboard shut down. You can close this tab.</div>'
    window.close()
  }

  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="app-header">
          <Link to="/" className="app-logo">
            <span className="logo-bracket">[</span>
            <span className="logo-text">{project || 'workflow'}</span>
            <span className="logo-bracket">]</span>
          </Link>
          <div className="header-line" />
          {cwd && <span className="header-cwd" title={cwd}>{cwd}</span>}
          <span className="header-tag">dashboard</span>
          <button className="close-btn" onClick={handleClose} title="Close dashboard">
            ✕
          </button>
        </header>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<RunList />} />
            <Route path="/runs/:id" element={<RunDetail />} />
            <Route path="/diff/:id1/:id2" element={<RunDiff />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
