import { useRunStore } from './store/runStore'
import { useAgentSocket } from './hooks/useAgentSocket'
import GoalInput   from './components/GoalInput'
import AgentLog    from './components/AgentLog'
import TaskDAG     from './components/TaskDAG'
import OutputPanel from './components/OutputPanel'
import './index.css'

export default function App() {
  const { runId } = useRunStore()

  // Connect WebSocket whenever runId changes
  useAgentSocket(runId)

  return (
    <div className="app">
      {/* Top bar */}
      <header className="app-header">
        <span className="header-logo">Agent<span>OS</span></span>
        <span className="header-sub">Multi-agent orchestration framework</span>
      </header>

      {/* Main layout */}
      <main className="app-main">

        {/* Left column — goal input + task graph */}
        <div className="col-left">
          <GoalInput />
          <TaskDAG />
        </div>

        {/* Right column — log + output */}
        <div className="col-right">
          <AgentLog />
          <OutputPanel />
        </div>

      </main>
    </div>
  )
}
