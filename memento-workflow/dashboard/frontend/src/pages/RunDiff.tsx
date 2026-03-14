import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import type { RunDiffResult, DiffEntry } from '../types'
import { fetchDiff } from '../api'
import StatusBadge from '../components/StatusBadge'

function DiffBlock({ entry }: { entry: DiffEntry }) {
  const [expanded, setExpanded] = useState(entry.change === 'modified')

  return (
    <div className="diff-entry">
      <div className="diff-entry-header" onClick={() => setExpanded(!expanded)}>
        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{expanded ? '▾' : '▸'}</span>
        <span>{entry.results_key}</span>
        <span className="diff-change-tag" data-change={entry.change}>{entry.change}</span>
        {entry.left && (
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)' }}>
            {entry.left.status}
            {entry.right && entry.right.status !== entry.left.status && ` → ${entry.right.status}`}
          </span>
        )}
      </div>

      {expanded && entry.artifact_diffs && entry.artifact_diffs.length > 0 && (
        <div className="diff-block">
          {entry.artifact_diffs.map((ad) => (
            <div key={ad.file}>
              <div className="diff-file-name">{ad.file}</div>
              <div className="diff-content">
                {ad.diff.split('\n').map((line, i) => {
                  let cls = 'diff-line-context'
                  if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-line-add'
                  else if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-line-remove'
                  else if (line.startsWith('@@')) cls = 'diff-line-header'
                  return <div key={i} className={cls}>{line}</div>
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {expanded && (!entry.artifact_diffs || entry.artifact_diffs.length === 0) && (
        <div className="diff-block">
          <div style={{ color: 'var(--text-muted)', fontSize: 11, padding: '8px 0' }}>
            {entry.change === 'unchanged' ? 'identical content' :
             entry.change === 'added' ? `step added (${entry.right?.status})` :
             entry.change === 'removed' ? `step removed (${entry.left?.status})` :
             'no artifact differences'}
          </div>
        </div>
      )}
    </div>
  )
}

export default function RunDiff() {
  const { id1, id2 } = useParams<{ id1: string; id2: string }>()
  const [result, setResult] = useState<RunDiffResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showUnchanged, setShowUnchanged] = useState(false)

  useEffect(() => {
    if (!id1 || !id2) return
    setLoading(true)
    fetchDiff(id1, id2)
      .then(setResult)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id1, id2])

  if (loading) {
    return <div className="loading-state"><div className="loading-pulse" /><span className="loading-label">computing diff</span></div>
  }

  if (error || !result) {
    return <div className="error-state"><span className="error-msg">{error || 'Diff failed'}</span></div>
  }

  const filtered = showUnchanged
    ? result.diffs
    : result.diffs.filter((d) => d.change !== 'unchanged')

  const counts = {
    added: result.diffs.filter((d) => d.change === 'added').length,
    removed: result.diffs.filter((d) => d.change === 'removed').length,
    modified: result.diffs.filter((d) => d.change === 'modified').length,
    unchanged: result.diffs.filter((d) => d.change === 'unchanged').length,
  }

  return (
    <div className="animate-in">
      <div className="breadcrumb">
        <Link to="/">runs</Link>
        <span className="sep">/</span>
        <span style={{ color: 'var(--text-primary)' }}>diff</span>
      </div>

      <div className="page-header">
        <div className="page-title">
          <span className="prefix">Δ</span>
          <Link to={`/runs/${id1}`} style={{ color: 'var(--text-primary)' }}>{id1?.slice(0, 8)}</Link>
          <span style={{ color: 'var(--text-muted)' }}>vs</span>
          <Link to={`/runs/${id2}`} style={{ color: 'var(--text-primary)' }}>{id2?.slice(0, 8)}</Link>
        </div>
        <div className="toolbar">
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            +{counts.added} −{counts.removed} ~{counts.modified} ={counts.unchanged}
          </span>
          <button
            className={`filter-btn${showUnchanged ? ' active' : ''}`}
            onClick={() => setShowUnchanged(!showUnchanged)}
          >
            show unchanged
          </button>
        </div>
      </div>

      <div className="diff-container animate-in stagger-1">
        <div className="diff-header">
          <div className="diff-header-cell">
            <StatusBadge status={result.run1.status} />
            <span style={{ marginLeft: 8, color: 'var(--text-secondary)' }}>
              {result.run1.workflow} — {result.run1.run_id.slice(0, 8)}
            </span>
          </div>
          <div className="diff-header-cell">
            <StatusBadge status={result.run2.status} />
            <span style={{ marginLeft: 8, color: 'var(--text-secondary)' }}>
              {result.run2.workflow} — {result.run2.run_id.slice(0, 8)}
            </span>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="empty-state" style={{ padding: '48px' }}>
            <span className="empty-label">
              {showUnchanged ? 'no steps to compare' : 'no differences found'}
            </span>
          </div>
        ) : (
          filtered.map((entry) => (
            <DiffBlock key={entry.results_key} entry={entry} />
          ))
        )}
      </div>
    </div>
  )
}
