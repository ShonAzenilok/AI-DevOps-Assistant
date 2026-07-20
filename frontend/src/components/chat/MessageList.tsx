import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage, ToolCall } from '../../types'
import { CheckIcon, ChevronIcon } from '../icons'
import { ActionCard } from './ActionCard'

function MarkdownText({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
  )
}

function formatDuration(ms?: number): string | null {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return null
  return `${(ms / 1000).toFixed(1)}s`
}

function ToolCard({ tools }: { tools: ToolCall[] }) {
  const [openRows, setOpenRows] = useState<Set<number>>(new Set())

  const toggle = (i: number) =>
    setOpenRows((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })

  return (
    <div className="tool-card">
      {tools.map((t, i) => {
        const hasOutput = Boolean(t.output && t.output.length > 0)
        const isOpen = hasOutput && openRows.has(i)
        return (
          <div key={i} className="tool-card__item">
            <button
              type="button"
              className="tool-card__row"
              onClick={() => hasOutput && toggle(i)}
              disabled={!hasOutput}
              aria-expanded={hasOutput ? isOpen : undefined}
              title={hasOutput ? 'Show tool output' : undefined}
            >
              <span className="tool-card__check" style={{ color: 'var(--bg)' }}>
                <CheckIcon size={8} strokeWidth={3.5} />
              </span>
              <span className="tool-card__label">{t.label}</span>
              <span className="tool-card__detail">{t.detail}</span>
              <span className="tool-card__duration">{formatDuration(t.durationMs)}</span>
              {hasOutput && (
                <span className={`tool-card__chevron${isOpen ? ' tool-card__chevron--open' : ''}`}>
                  <ChevronIcon size={12} />
                </span>
              )}
            </button>
            {isOpen && <pre className="tool-card__output">{t.output}</pre>}
          </div>
        )
      })}
    </div>
  )
}

/** Reserves room below the last message equal to the scroll viewport's
 * height, so a just-sent question can always be scrolled flush to the top
 * even before its answer has streamed in (otherwise there's nothing below
 * it yet to scroll into view — the classic ChatGPT-style spacer trick). */
function BottomSpacer() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    const scrollEl = el?.closest('.chat-scroll')
    if (!el || !scrollEl) return
    const update = () => {
      el.style.height = `${scrollEl.clientHeight}px`
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(scrollEl)
    return () => observer.disconnect()
  }, [])

  return <div ref={ref} aria-hidden="true" className="chat-bottom-spacer" />
}

interface MessageListProps {
  appName: string
  messages: ChatMessage[]
  isThinking: boolean
  onResolveAction: (messageId: string, actionId: string, verb: 'confirm' | 'cancel') => void
}

export function MessageList({ appName, messages, isThinking, onResolveAction }: MessageListProps) {
  const rowRefs = useRef(new Map<string, HTMLDivElement>())
  const lastScrolledUserId = useRef<string | null>(null)

  // Chat-app style: when a new question is asked, scroll it to the top of the
  // viewport (like ChatGPT) instead of chasing the bottom as the answer
  // streams in — older turns stay scrollable above it.
  useEffect(() => {
    let lastUser: ChatMessage | undefined
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastUser = messages[i]
        break
      }
    }
    if (!lastUser || lastUser.id === lastScrolledUserId.current) return
    lastScrolledUserId.current = lastUser.id
    const id = lastUser.id
    // Defer a frame: the spacer/new row have just mounted, so their layout
    // may not be committed yet — measuring now can scroll to a stale position.
    requestAnimationFrame(() => {
      rowRefs.current.get(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [messages])

  return (
    <>
      {messages.map((m) => (
        <div
          key={m.id}
          className="message-row"
          ref={(el) => {
            if (el) rowRefs.current.set(m.id, el)
            else rowRefs.current.delete(m.id)
          }}
        >
          {m.role === 'user' ? (
            <div className="user-bubble">{m.text}</div>
          ) : (
            <div className="assistant-message">
              <div className={`assistant-message__text${m.isError ? ' assistant-message__text--error' : ''}`}>
                {m.isError ? m.text : <MarkdownText text={m.text} />}
              </div>
              {m.tools && m.tools.length > 0 && <ToolCard tools={m.tools} />}
              {m.actions?.map((a) => (
                <ActionCard
                  key={a.id}
                  action={a}
                  onResolve={(actionId, verb) => onResolveAction(m.id, actionId, verb)}
                />
              ))}
            </div>
          )}
        </div>
      ))}
      {isThinking && (
        <div className="thinking-row">
          <span className="thinking-row__dot" />
          {appName} is working on it…
        </div>
      )}
      {messages.length > 0 && <BottomSpacer />}
    </>
  )
}
