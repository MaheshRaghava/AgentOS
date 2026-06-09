import { useState } from 'react'
import { useRunStore } from '../store/runStore'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const EXAMPLE_GOALS = [
  'Research the top 3 JavaScript frameworks and compare their pros and cons',
  'Write a Python function to find all prime numbers up to N using the Sieve of Eratosthenes',
  'Research the latest trends in AI in 2025 and summarize key developments',
]

export default function GoalInput() {
  const [input, setInput] = useState('')
  const { startRun, addLogLine, setLoading, isLoading, runStatus } = useRunStore()

  const isRunning = runStatus === 'running' || runStatus === 'planning'

  async function handleSubmit() {
    const goal = input.trim()
    if (!goal) return

    setLoading(true)
    addLogLine({ type: 'system', text: `Submitting goal: "${goal}"` })

    try {
      const res = await fetch(`${API_BASE}/api/goal`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ goal }),
      })

      if (!res.ok) {
        const err = await res.json()
        const msg = err.detail || 'Request failed'
        alert(msg)
        
        // Use 'system' type for 400 responses (greetings, incomplete goals)
        if (res.status === 400) {
          addLogLine({ type: 'system', text: msg })
        } else {
          addLogLine({ type: 'error', text: `Failed: ${msg}` })
        }
        return
      }

      const data = await res.json()
      startRun(data.run_id)
      addLogLine({ type: 'success', text: `Run started — ID: ${data.run_id}` })

    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      addLogLine({ type: 'error', text: `Failed to start run: ${msg}` })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="goal-input-panel">
      <div className="goal-header">
        <h1 className="logo">Agent<span>OS</span></h1>
        <p className="tagline">Multi-agent task orchestration</p>
      </div>

      <div className="goal-form">
        <textarea
          className="goal-textarea"
          placeholder="Describe what you want the agents to do..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isRunning}
          rows={3}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit()
          }}
        />
        <div className="goal-actions">
          <span className="hint">Ctrl+Enter to run</span>
          <button
            className={`run-btn ${isRunning ? 'running' : ''}`}
            onClick={handleSubmit}
            disabled={isRunning || isLoading}
          >
            {isLoading ? 'Starting...' : isRunning ? '⏳ Running...' : '▶ Run Agents'}
          </button>
        </div>
      </div>

      <div className="examples">
        <p className="examples-label">Try an example:</p>
        <div className="example-pills">
          {EXAMPLE_GOALS.map((g, i) => (
            <button
              key={i}
              className="example-pill"
              onClick={() => setInput(g)}
              disabled={isRunning}
            >
              {g.slice(0, 55)}…
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}