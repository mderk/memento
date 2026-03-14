import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
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

    // Signal server on tab close (not refresh).
    // pagehide fires on both close and refresh, but on refresh the new page
    // immediately sends /api/cancel-shutdown to abort.
    const onPageHide = () => {
      navigator.sendBeacon('/api/tab-closed')
    }
    window.addEventListener('pagehide', onPageHide)

    // On load: cancel any pending shutdown (covers refresh)
    navigator.sendBeacon('/api/cancel-shutdown')

    return () => window.removeEventListener('pagehide', onPageHide)
  }, [])

  const handleClose = () => {
    requestShutdown()
    window.close()
  }

  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="app-header">
          <a href="/" className="app-logo">
            <span className="logo-bracket">[</span>
            <span className="logo-text">{project || 'workflow'}</span>
            <span className="logo-bracket">]</span>
          </a>
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
