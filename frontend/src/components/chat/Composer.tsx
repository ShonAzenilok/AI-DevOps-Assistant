import { useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { SendIcon } from '../icons'

const MAX_HEIGHT = 160

interface ComposerProps {
  isThinking: boolean
  onSend: (text: string) => void
}

export function Composer({ isThinking, onSend }: ComposerProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(el.scrollHeight, MAX_HEIGHT)
    el.style.height = `${next}px`
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden'
  }

  const submit = () => {
    const text = input.trim()
    if (!text || isThinking) return
    onSend(text)
    setInput('')
    requestAnimationFrame(autoGrow)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const disabled = !input.trim() || isThinking

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={textareaRef}
          value={input}
          rows={1}
          placeholder="Ask about your AWS resources, logs, or provision changes..."
          onChange={(e) => {
            setInput(e.target.value)
            autoGrow()
          }}
          onKeyDown={onKeyDown}
        />
        <div className="composer__actions">
          <button type="button" className="composer__send" disabled={disabled} onClick={submit} title="Send">
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  )
}
