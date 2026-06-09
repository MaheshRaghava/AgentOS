import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useRunStore } from '../store/runStore'

const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  pending:  { bg: '#1e1e2e', border: '#4b5563', text: '#9ca3af' },
  running:  { bg: '#451a03', border: '#f59e0b', text: '#fcd34d' },
  done:     { bg: '#052e16', border: '#10b981', text: '#6ee7b7' },
  failed:   { bg: '#450a0a', border: '#ef4444', text: '#fca5a5' },
  skipped:  { bg: '#1e1e2e', border: '#6b7280', text: '#6b7280' },
}

const WORKER_ICONS: Record<string, string> = {
  researcher:  '🔍',
  summarizer:  '📝',
  coder:       '💻',
  browser:     '🌐',
  synthesizer: '✨',
}

export default function TaskDAG() {
  const { tasks } = useRunStore()
  const [isFullscreen, setIsFullscreen] = useState(false)

  const { nodes, edges } = useMemo(() => {
    if (!tasks.length) return { nodes: [], edges: [] }

    const depthMap: Record<string, number> = {}

    function getDepth(taskId: string, visited = new Set<string>()): number {
      if (depthMap[taskId] !== undefined) return depthMap[taskId]
      if (visited.has(taskId)) return 0
      visited.add(taskId)
      const task = tasks.find((t) => t.id === taskId)
      if (!task || !task.dependencies?.length) {
        depthMap[taskId] = 0
        return 0
      }
      const maxDepDep = Math.max(...task.dependencies.map((d) => getDepth(d, visited)))
      depthMap[taskId] = maxDepDep + 1
      return depthMap[taskId]
    }

    tasks.forEach((t) => getDepth(t.id))

    const byDepth: Record<number, typeof tasks> = {}
    tasks.forEach((t) => {
      const d = depthMap[t.id] || 0
      byDepth[d] = byDepth[d] || []
      byDepth[d].push(t)
    })

    const NODE_W = 180
    const NODE_H = 70
    const GAP_X = 60
    const GAP_Y = 100

    const nodes: Node[] = tasks.map((task) => {
      const depth = depthMap[task.id] || 0
      const siblings = byDepth[depth] || []
      const idx = siblings.indexOf(task)
      const totalW = siblings.length * (NODE_W + GAP_X) - GAP_X
      const x = idx * (NODE_W + GAP_X) - totalW / 2 + 300
      const y = depth * (NODE_H + GAP_Y) + 40

      const colors = STATUS_COLORS[task.status] || STATUS_COLORS.pending
      const icon = WORKER_ICONS[task.worker] || '🤖'

      return {
        id: task.id,
        position: { x, y },
        type: 'default',
        style: {
          background:   colors.bg,
          border:       `1.5px solid ${colors.border}`,
          borderRadius: '10px',
          padding:      '10px 14px',
          minWidth:     `${NODE_W}px`,
          color:        colors.text,
          fontSize:     '12px',
          boxShadow:    task.status === 'running' ? `0 0 12px ${colors.border}` : 'none',
          transition:   'all 0.3s ease',
        },
        data: {
          label: (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 18, marginBottom: 2 }}>{icon}</div>
              <div style={{ fontWeight: 600, fontSize: 11, color: colors.text }}>
                {task.name.replace(/_/g, ' ')}
              </div>
              <div style={{
                fontSize: 10,
                marginTop: 3,
                padding: '1px 6px',
                borderRadius: 99,
                background: colors.border + '33',
                color: colors.border,
                display: 'inline-block',
              }}>
                {task.status}
              </div>
            </div>
          ),
        },
      }
    })

    const edges: Edge[] = tasks.flatMap((task) =>
      (task.dependencies || []).map((depId) => ({
        id:            `${depId}-${task.id}`,
        source:        depId,
        target:        task.id,
        animated:      task.status === 'running',
        style:         { stroke: '#4b5563', strokeWidth: 1.5 },
        markerEnd:     { type: 'arrowclosed' as const, color: '#4b5563' },
      }))
    )

    return { nodes, edges }
  }, [tasks])

  const dagContent = (
    <>
      <div className="dag-header">
        <span className="dag-title">Task Graph</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="dag-count">{tasks.length} tasks</span>
          {tasks.length > 0 && (
            <button
              className="dag-expand-btn"
              onClick={() => setIsFullscreen(!isFullscreen)}
              title={isFullscreen ? 'Exit fullscreen' : 'Expand to fullscreen'}
            >
              {isFullscreen ? '✕' : '⛶'}
            </button>
          )}
        </div>
      </div>

      <div className="dag-canvas">
        {tasks.length === 0 ? (
          <div className="dag-empty">
            <p>Task graph will appear here</p>
            <p style={{ fontSize: 12, opacity: 0.5, marginTop: 8 }}>
              Submit a goal to start
            </p>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            nodesDraggable={true}
            nodesConnectable={false}
            elementsSelectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#333" gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
    </>
  )

  return (
    <>
      {/* Normal view */}
      <div className="task-dag">
        {dagContent}
      </div>

      {/* Fullscreen overlay */}
      {isFullscreen && (
        <div 
          className="dag-fullscreen-overlay" 
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsFullscreen(false)
          }}
        >
          <div className="dag-fullscreen-panel">
            <div className="dag-fullscreen-header">
              <span className="dag-fullscreen-title">Task Graph</span>
              <button
                className="dag-fullscreen-close"
                onClick={() => setIsFullscreen(false)}
              >
                ✕
              </button>
            </div>
            <div className="dag-fullscreen-canvas">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                nodesDraggable={true}
                nodesConnectable={false}
                elementsSelectable={false}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#333" gap={20} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          </div>
        </div>
      )}
    </>
  )
}