import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import type { RunDetail as RunDetailType, StepInfo } from '../types'
import { fetchRunDetail, fetchArtifact } from '../api'
import StatusBadge from '../components/StatusBadge'
import Timeline from '../components/Timeline'

function formatTime(iso: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function formatDuration(start: string, end: string | null): string {
  if (!start) return '—'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const sec = Math.round((e - s) / 1000)
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<RunDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeStep, setActiveStep] = useState<StepInfo | null>(null)
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null)
  const [artifactContent, setArtifactContent] = useState<string | null>(null)
  const [artifactLoading, setArtifactLoading] = useState(false)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    fetchRunDetail(id)
      .then((d) => {
        setDetail(d)
        if (d.steps.length > 0) setActiveStep(d.steps[0])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  // Refresh running runs
  useEffect(() => {
    if (!detail || detail.meta.status !== 'running' || !id) return
    const interval = setInterval(() => {
      fetchRunDetail(id).then(setDetail).catch(() => {})
    }, 3000)
    return () => clearInterval(interval)
  }, [detail?.meta.status, id])

  // Load artifact content when selected
  useEffect(() => {
    if (!id || !activeStep || !activeArtifact) {
      setArtifactContent(null)
      return
    }
    setArtifactLoading(true)
    // Build the artifact path: must mirror scripts/artifacts.py logic
    const execPath = activeStep.exec_key
      .replace(/:/g, '-')
      .replace(/\[(\w+)=(\d+)\]/g, '/$1-$2')
    fetchArtifact(id, `${execPath}/${activeArtifact}`)
      .then(setArtifactContent)
      .catch(() => setArtifactContent(null))
      .finally(() => setArtifactLoading(false))
  }, [id, activeStep?.exec_key, activeArtifact])

  if (loading) {
    return <div className="loading-state"><div className="loading-pulse" /><span className="loading-label">loading run</span></div>
  }

  if (error || !detail) {
    return <div className="error-state"><span className="error-msg">{error || 'Run not found'}</span></div>
  }

  const { meta, steps } = detail

  return (
    <div className="animate-in detail-page">
      <div className="detail-header-compact">
        <div className="breadcrumb" style={{ marginBottom: 0 }}>
          <Link to="/">runs</Link>
          <span className="sep">/</span>
          <span style={{ color: 'var(--text-primary)' }}>{id}</span>
        </div>
        <span className="detail-meta-inline">
          {meta.workflow && <span className="meta-tag">{meta.workflow}</span>}
          <StatusBadge status={meta.status} />
          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
            {formatTime(meta.started_at)}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
            {formatDuration(meta.started_at, meta.completed_at)}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
            {steps.length} steps
          </span>
        </span>
      </div>

      <div className="detail-grid animate-in stagger-1">
        <div className="detail-sidebar">
          <Timeline
            steps={steps}
            activeKey={activeStep?.exec_key ?? null}
            onSelect={(step) => {
              setActiveStep(step)
              setActiveArtifact(null)
              setArtifactContent(null)
            }}
          />
        </div>
        <div className="detail-content">
          {activeStep ? (
            <div className="artifact-viewer">
              <div className="viewer-toolbar">
                <span style={{ color: 'var(--text-muted)' }}>step:</span>
                <span className="viewer-path">{activeStep.name}</span>
                {activeStep.artifact_files.length > 0 && (
                  <div className="artifact-file-tabs">
                    <button
                      className={`artifact-tab${activeArtifact === null ? ' active' : ''}`}
                      onClick={() => { setActiveArtifact(null); setArtifactContent(null) }}
                    >
                      output
                    </button>
                    {activeStep.artifact_files.map((f) => (
                      <button
                        key={f}
                        className={`artifact-tab${activeArtifact === f ? ' active' : ''}`}
                        onClick={() => setActiveArtifact(f)}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="viewer-content">
                {activeArtifact ? (
                  artifactLoading ? (
                    <div className="loading-state" style={{ padding: 24 }}><div className="loading-pulse" /></div>
                  ) : (
                    <pre>{artifactContent ?? '(empty)'}</pre>
                  )
                ) : (
                  <>
                    <pre>{activeStep.output_preview || '(no output)'}</pre>
                    {activeStep.error && (
                      <pre style={{ color: 'var(--status-error)', marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                        {activeStep.error}
                      </pre>
                    )}
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="viewer-empty">select a step</div>
          )}
        </div>
      </div>
    </div>
  )
}
