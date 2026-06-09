import { useEffect, useRef } from 'react'
import { useRunStore } from '../store/runStore'

export default function AgentLog() {
  const { logLines, runStatus, runId } = useRunStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logLines])

  const statusColor: Record<string, string> = {
    idle:      '#888',
    planning:  '#a78bfa',
    running:   '#f59e0b',
    completed: '#10b981',
    failed:    '#ef4444',
  }

  return (
    <div className="agent-log">
      <div className="log-header">
        <span className="log-title">Agent Log</span>
        <span
          className="run-status-badge"
          style={{ background: statusColor[runStatus] || '#888' }}
        >
          {runStatus}
        </span>
      </div>

      <div className="log-body">
        {logLines.length === 0 ? (
          <p className="log-empty">Waiting for agents to start...</p>
        ) : (
          logLines.map((line) => (
            <div key={line.id} className={`log-line log-${line.type}`}>
              <span className="log-ts">{line.ts}</span>
              <span className="log-text">{line.text}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {runId && (
        <div className="log-footer">
          <span className="run-id-label">run: {runId.slice(0, 12)}...</span>
        </div>
      )}
    </div>
  )
}
