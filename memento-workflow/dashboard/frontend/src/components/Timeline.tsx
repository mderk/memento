import type { StepInfo } from '../types'

interface Props {
  steps: StepInfo[]
  activeKey: string | null
  onSelect: (step: StepInfo) => void
}

function formatDuration(s: number): string {
  if (s < 1) return `${Math.round(s * 1000)}ms`
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

/** Count '/' in exec_key to determine nesting depth */
function execKeyDepth(key: string): number {
  return (key.match(/\//g) || []).length
}

/** Extract the last segment name from exec_key, stripped of type prefixes and indices */
function shortName(execKey: string): string {
  const parts = execKey.split('/')
  const last = parts[parts.length - 1]
  // strip type prefix (par:, loop:, par-batch:, etc) and index suffix [i=N]
  return last.replace(/^[\w-]+:/, '').replace(/\[[\w]+=\d+\]/, '')
}

export default function Timeline({ steps, activeKey, onSelect }: Props) {
  return (
    <div className="timeline">
      {steps.map((step, i) => {
        const depth = execKeyDepth(step.exec_key)
        return (
          <div
            key={step.exec_key}
            className={`timeline-item${activeKey === step.exec_key ? ' active' : ''}`}
            onClick={() => onSelect(step)}
          >
            <div className="timeline-rail" style={{ marginLeft: depth * 12 }}>
              <div className="timeline-dot" data-status={step.status} />
              {i < steps.length - 1 && <div className="timeline-line" />}
            </div>
            <div className="timeline-body">
              <div className="timeline-name">{shortName(step.exec_key)}</div>
              <div className="timeline-meta">
                <span>{formatDuration(step.duration)}</span>
                {step.cost_usd != null && <span>${step.cost_usd.toFixed(4)}</span>}
                {step.error && <span style={{ color: 'var(--status-error)' }}>err</span>}
                {step.artifact_files.length > 0 && (
                  <span style={{ color: 'var(--text-muted)' }}>{step.artifact_files.length} files</span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
