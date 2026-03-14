import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import type { RunListItem } from '../types'
import { fetchRuns, connectWS } from '../api'
import StatusBadge from '../components/StatusBadge'

type SortKey = 'workflow' | 'status' | 'started_at' | 'step_count'
type StatusFilter = 'all' | 'running' | 'completed' | 'error' | 'cancelled'

function formatDateTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
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

function sortTimestamp(a: string, b: string): number {
  const ta = a ? new Date(a).getTime() : 0
  const tb = b ? new Date(b).getTime() : 0
  return ta - tb
}

/** Render a single run row + its children recursively */
function RunRow({
  run,
  depth,
  selected,
  onSelect,
  onNavigate,
  expanded,
  onToggleExpand,
}: {
  run: RunListItem
  depth: number
  selected: Set<string>
  onSelect: (id: string, e: React.MouseEvent) => void
  onNavigate: (id: string) => void
  expanded: Set<string>
  onToggleExpand: (id: string, e: React.MouseEvent) => void
}) {
  const hasChildren = run.children && run.children.length > 0
  const isExpanded = expanded.has(run.run_id)

  return (
    <>
      <tr
        className={`clickable${selected.has(run.run_id) ? ' selected' : ''}`}
        onClick={() => onNavigate(run.run_id)}
      >
        <td onClick={(e) => onSelect(run.run_id, e)}>
          <input
            type="checkbox"
            checked={selected.has(run.run_id)}
            readOnly
            style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
        </td>
        <td>
          <span style={{ paddingLeft: depth * 20, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {hasChildren && (
              <span
                className="tree-toggle"
                onClick={(e) => onToggleExpand(run.run_id, e)}
              >
                {isExpanded ? '▾' : '▸'}
              </span>
            )}
            {depth > 0 && !hasChildren && <span style={{ width: 12, display: 'inline-block' }} />}
            {depth > 0 && <span style={{ color: 'var(--border-active)', marginRight: 2 }}>└</span>}
            <span className="mono-id">{run.run_id.slice(0, 8)}</span>
          </span>
        </td>
        <td>{run.workflow || <span style={{ color: 'var(--text-muted)' }}>—</span>}</td>
        <td><StatusBadge status={run.status} /></td>
        <td style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {formatDateTime(run.started_at)}
        </td>
        <td style={{ color: 'var(--text-secondary)' }}>
          {formatDuration(run.started_at, run.completed_at)}
        </td>
        <td style={{ textAlign: 'right' }}>{run.step_count}</td>
        <td style={{ color: 'var(--text-muted)', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {depth === 0 ? (run.cwd || '—') : ''}
        </td>
      </tr>
      {hasChildren && isExpanded && run.children.map((child) => (
        <RunRow
          key={child.run_id}
          run={child}
          depth={depth + 1}
          selected={selected}
          onSelect={onSelect}
          onNavigate={onNavigate}
          expanded={expanded}
          onToggleExpand={onToggleExpand}
        />
      ))}
    </>
  )
}

export default function RunList() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('started_at')
  const [sortAsc, setSortAsc] = useState(false)
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchRuns()
      .then(setRuns)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const disconnect = connectWS((msg) => {
      setRuns((prev) => {
        if (msg.type === 'run_new') {
          return [msg.run, ...prev.filter((r) => r.run_id !== msg.run.run_id)]
        }
        if (msg.type === 'run_update') {
          return prev.map((r) => r.run_id === msg.run.run_id ? msg.run : r)
        }
        if (msg.type === 'run_removed') {
          return prev.filter((r) => r.run_id !== msg.run_id)
        }
        return prev
      })
    })
    return disconnect
  }, [])

  const toggleSort = useCallback((key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(key === 'started_at' ? false : true) }
  }, [sortKey, sortAsc])

  const toggleSelect = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 2) next.add(id)
      else {
        const arr = Array.from(next)
        next.delete(arr[0])
        next.add(id)
      }
      return next
    })
  }, [])

  const toggleExpand = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const filtered = runs.filter((r) => filter === 'all' || r.status === filter)
  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'workflow') cmp = a.workflow.localeCompare(b.workflow)
    else if (sortKey === 'status') cmp = a.status.localeCompare(b.status)
    else if (sortKey === 'started_at') cmp = sortTimestamp(a.started_at, b.started_at)
    else if (sortKey === 'step_count') cmp = a.step_count - b.step_count
    return sortAsc ? cmp : -cmp
  })

  const canCompare = selected.size === 2

  if (loading) {
    return <div className="loading-state"><div className="loading-pulse" /><span className="loading-label">loading runs</span></div>
  }

  if (error) {
    return <div className="error-state"><span className="error-msg">{error}</span></div>
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div className="page-title">
          <span className="prefix">&gt;</span> runs
          <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 12 }}>
            ({filtered.length})
          </span>
        </div>
        <div className="toolbar">
          {(['all', 'running', 'completed', 'error', 'cancelled'] as StatusFilter[]).map((f) => (
            <button
              key={f}
              className={`filter-btn${filter === f ? ' active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
          <button
            className="btn-primary"
            disabled={!canCompare}
            onClick={() => {
              const [a, b] = Array.from(selected)
              navigate(`/diff/${a}/${b}`)
            }}
          >
            compare {canCompare ? `(${selected.size})` : ''}
          </button>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="empty-state">
          <span className="empty-label">no workflow runs found</span>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 32 }} />
              <th style={{ width: 140 }}>run id</th>
              <th className={sortKey === 'workflow' ? 'sorted' : ''} onClick={() => toggleSort('workflow')}>
                workflow {sortKey === 'workflow' ? (sortAsc ? '↑' : '↓') : ''}
              </th>
              <th className={sortKey === 'status' ? 'sorted' : ''} onClick={() => toggleSort('status')} style={{ width: 120 }}>
                status {sortKey === 'status' ? (sortAsc ? '↑' : '↓') : ''}
              </th>
              <th className={sortKey === 'started_at' ? 'sorted' : ''} onClick={() => toggleSort('started_at')} style={{ width: 200 }}>
                date / time {sortKey === 'started_at' ? (sortAsc ? '↑' : '↓') : ''}
              </th>
              <th style={{ width: 100 }}>duration</th>
              <th className={sortKey === 'step_count' ? 'sorted' : ''} onClick={() => toggleSort('step_count')} style={{ width: 80, textAlign: 'right' }}>
                steps {sortKey === 'step_count' ? (sortAsc ? '↑' : '↓') : ''}
              </th>
              <th>cwd</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((run) => (
              <RunRow
                key={run.run_id}
                run={run}
                depth={0}
                selected={selected}
                onSelect={toggleSelect}
                onNavigate={(id) => navigate(`/runs/${id}`)}
                expanded={expanded}
                onToggleExpand={toggleExpand}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
