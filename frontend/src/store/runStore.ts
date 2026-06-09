import { create } from 'zustand'
import type { TaskNode } from '../hooks/useAgentSocket'

export interface LogLine {
  id:   number
  type: 'system' | 'info' | 'success' | 'error'
  text: string
  ts:   string
}

interface RunState {
  // Current run
  runId:       string | null
  goal:        string
  runStatus:   string   // planning | running | completed | failed | idle
  tasks:       TaskNode[]
  logLines:    LogLine[]
  finalOutput: string
  isLoading:   boolean

  // Actions
  startRun:      (runId: string) => void
  setGoal:       (goal: string) => void
  setRunStatus:  (status: string) => void
  setTasks:      (tasks: TaskNode[]) => void
  updateTask:    (partial: Partial<TaskNode> & { id: string }) => void
  addLogLine:    (line: Omit<LogLine, 'id' | 'ts'>) => void
  setFinalOutput:(output: string) => void
  setLoading:    (v: boolean) => void
  reset:         () => void
}

let logCounter = 0

export const useRunStore = create<RunState>((set) => ({
  runId:       null,
  goal:        '',
  runStatus:   'idle',
  tasks:       [],
  logLines:    [],
  finalOutput: '',
  isLoading:   false,

  startRun: (runId) => set({
    runId,
    runStatus:   'planning',
    tasks:       [],
    logLines:    [],
    finalOutput: '',
  }),

  setGoal:      (goal)   => set({ goal }),
  setRunStatus: (status) => set({ runStatus: status }),
  setTasks:     (tasks)  => set({ tasks }),

  updateTask: (partial) => set((state) => ({
    tasks: state.tasks.map((t) =>
      t.id === partial.id ? { ...t, ...partial } : t
    ),
  })),

  addLogLine: (line) => set((state) => ({
    logLines: [
      ...state.logLines,
      {
        ...line,
        id: ++logCounter,
        ts: new Date().toLocaleTimeString(),
      },
    ].slice(-200), // keep last 200 lines
  })),

  setFinalOutput: (output) => set({ finalOutput: output }),
  setLoading:     (v)      => set({ isLoading: v }),

  reset: () => set({
    runId:       null,
    goal:        '',
    runStatus:   'idle',
    tasks:       [],
    logLines:    [],
    finalOutput: '',
    isLoading:   false,
  }),
}))
