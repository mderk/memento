export interface RunListItem {
  run_id: string
  workflow: string
  status: 'running' | 'completed' | 'error' | 'cancelled' | 'unknown'
  started_at: string
  completed_at: string | null
  step_count: number
  cwd: string
  parent_run_id: string | null
  child_run_ids: string[]
  children: RunListItem[]
}

export interface StepInfo {
  exec_key: string
  results_key: string
  name: string
  status: string
  output_preview: string
  duration: number
  error: string | null
  cost_usd: number | null
  order: number
  artifact_files: string[]
}

export interface ArtifactNode {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number
  children?: ArtifactNode[]
}

export interface RunDetail {
  meta: RunListItem
  steps: StepInfo[]
  artifact_tree: ArtifactNode[]
}

export interface DiffEntry {
  results_key: string
  change: 'added' | 'removed' | 'modified' | 'unchanged'
  left?: StepInfo
  right?: StepInfo
  artifact_diffs?: Array<{ file: string; diff: string }>
}

export interface RunDiffResult {
  run1: RunListItem
  run2: RunListItem
  diffs: DiffEntry[]
}

export type WSMessage =
  | { type: 'run_update'; run: RunListItem }
  | { type: 'run_new'; run: RunListItem }
  | { type: 'run_removed'; run_id: string }
