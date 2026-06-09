import { useEffect, useRef } from 'react'
import { useRunStore } from '../store/runStore'

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

export interface TaskNode {
  id:           string
  name:         string
  worker:       string
  status:       string
  description?: string
  dependencies?: string[]
  output?:      string
  error?:       string
}

export function useAgentSocket(runId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const {
    setRunStatus,
    setGoal,
    setTasks,
    updateTask,
    addLogLine,
    setFinalOutput,
  } = useRunStore()

  useEffect(() => {
    if (!runId) return

    if (wsRef.current) {
      wsRef.current.close()
    }

    const ws = new WebSocket(`${WS_BASE}/api/ws/${runId}`)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[WS] Connected for run:', runId)
      addLogLine({ type: 'system', text: `Connected to run ${runId}` })
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        console.log('[WS] Message received:', msg)
        
        // Handle different event formats
        const eventType = msg.event || msg.type
        
        if (eventType === 'run_state') {
          const data = msg.data || msg
          console.log('[WS] run_state:', data)
          setGoal(data.goal)
          setRunStatus(data.status)
          if (data.tasks) {
            setTasks(data.tasks)
          }
          addLogLine({ type: 'system', text: `Run loaded — ${data.tasks?.length || 0} tasks planned` })
        }
        else if (eventType === 'task_update') {
          const data = msg.data || msg
          const status = data.status
          const taskId = data.task_id || data.id
          const taskName = data.name
          
          if (taskId && taskName) {
            updateTask({
              id: taskId,
              name: taskName,
              status: status,
              output: data.output_preview,
              error: data.error,
            })
            const icon = status === 'done' ? '✓' : status === 'failed' ? '✗' : status === 'running' ? '▶' : '○'
            addLogLine({
              type: status === 'failed' ? 'error' : status === 'done' ? 'success' : 'info',
              text: `${icon} [${taskName}] → ${status}${data.error ? ': ' + data.error : ''}`,
            })
          }
        }
        else if (eventType === 'final_output') {
          const data = msg.data || msg
          console.log('[WS] final_output received')
          setFinalOutput(data.output)
          setRunStatus('completed')
          addLogLine({ type: 'success', text: '✓ Run completed — final output ready' })
        }
        else if (eventType === 'run_completed') {
          setRunStatus('completed')
        }
        else if (eventType === 'run_failed') {
          setRunStatus('failed')
          addLogLine({ type: 'error', text: '✗ Run failed' })
        }
      } catch (e) {
        console.error('[WS] Parse error:', e, event.data)
      }
    }

    ws.onerror = (e) => {
      console.error('[WS] Error:', e)
      addLogLine({ type: 'error', text: 'WebSocket error — check console' })
    }

    ws.onclose = () => {
      console.log('[WS] Disconnected')
      addLogLine({ type: 'system', text: 'Disconnected from run' })
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [runId, addLogLine, setFinalOutput, setGoal, setRunStatus, setTasks, updateTask])
}