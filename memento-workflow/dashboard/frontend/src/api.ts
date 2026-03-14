import type { RunListItem, RunDetail, RunDiffResult, WSMessage } from './types'

const BASE = ''

export interface ProjectInfo {
  project: string
  cwd: string
}

export async function fetchInfo(): Promise<ProjectInfo> {
  const res = await fetch(`${BASE}/api/info`)
  if (!res.ok) throw new Error(`Failed to fetch info: ${res.status}`)
  return res.json()
}

export function requestShutdown(): void {
  navigator.sendBeacon(`${BASE}/api/shutdown`)
}

export async function fetchRuns(): Promise<RunListItem[]> {
  const res = await fetch(`${BASE}/api/runs`)
  if (!res.ok) throw new Error(`Failed to fetch runs: ${res.status}`)
  return res.json()
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const res = await fetch(`${BASE}/api/runs/${runId}`)
  if (!res.ok) throw new Error(`Failed to fetch run: ${res.status}`)
  return res.json()
}

export async function fetchArtifact(runId: string, path: string): Promise<string> {
  const res = await fetch(`${BASE}/api/runs/${runId}/artifacts/${path}`)
  if (!res.ok) throw new Error(`Failed to fetch artifact: ${res.status}`)
  return res.text()
}

export async function fetchDiff(id1: string, id2: string): Promise<RunDiffResult> {
  const res = await fetch(`${BASE}/api/diff/${id1}/${id2}`)
  if (!res.ok) throw new Error(`Failed to fetch diff: ${res.status}`)
  return res.json()
}

export function connectWS(onMessage: (msg: WSMessage) => void): () => void {
  let ws: WebSocket | null = null
  let closed = false
  let reconnectTimer: ReturnType<typeof setTimeout>

  function connect() {
    if (closed) return
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${location.host}/api/ws`)

    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data))
      } catch {}
    }

    ws.onclose = () => {
      if (!closed) {
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => ws?.close()
  }

  connect()

  return () => {
    closed = true
    clearTimeout(reconnectTimer)
    ws?.close()
  }
}
