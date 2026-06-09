import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useRunStore } from '../store/runStore'

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button className="code-copy-btn" onClick={handleCopy}>
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

function CodeBlock({ children, className }: { children?: React.ReactNode; className?: string }) {
  const code = String(children ?? '').replace(/\n$/, '')
  const language = className?.replace('language-', '') ?? ''

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        {language && <span className="code-language">{language}</span>}
        <CopyButton text={code} />
      </div>
      <pre className="code-block-pre">
        <code className={className}>{code}</code>
      </pre>
    </div>
  )
}

export default function OutputPanel() {
  const { finalOutput, runStatus, goal } = useRunStore()
  const [outputCopied, setOutputCopied] = useState(false)

  function copyOutput() {
    navigator.clipboard.writeText(finalOutput).then(() => {
      setOutputCopied(true)
      setTimeout(() => setOutputCopied(false), 2000)
    })
  }

  return (
    <div className="output-panel">
      <div className="output-header">
        <span className="output-title">Final Output</span>
        {finalOutput && (
          <button className="copy-output-btn" onClick={copyOutput}>
            {outputCopied ? '✓ Copied' : 'Copy'}
          </button>
        )}
      </div>

      <div className="output-body">
        {!finalOutput && runStatus === 'idle' && (
          <div className="output-empty">
            <p>Final answer will appear here</p>
            <p style={{ fontSize: 12, opacity: 0.5, marginTop: 8 }}>
              Agents will research, analyze, and synthesize a response
            </p>
          </div>
        )}

        {!finalOutput && runStatus !== 'idle' && (
          <div className="output-waiting">
            <div className="spinner" />
            <p>Agents working on: <em>{goal}</em></p>
          </div>
        )}

        {finalOutput && (
          <div className="markdown-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, className, children, ...props }: any) {
                  const isBlock = className?.startsWith('language-') || String(children).includes('\n')
                  if (isBlock) {
                    return <CodeBlock className={className}>{children}</CodeBlock>
                  }
                  // Inline code — no copy button
                  return <code className={className} {...props}>{children}</code>
                }
              }}
            >
              {finalOutput}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
