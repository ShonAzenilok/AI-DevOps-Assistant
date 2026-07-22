import { useState, type FormEvent } from 'react'
import './App.css'

export default function App() {
  const [name, setName] = useState('')
  const [greeting, setGreeting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setGreeting(null)
    setError(null)
    setLoading(true)
    try {
      const res = await fetch('/api/hello', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const data = (await res.json()) as { message?: string; error?: string }
      if (!res.ok) {
        setError(data.error || 'Something went wrong')
        return
      }
      setGreeting(data.message ?? null)
    } catch {
      setError('Could not reach the server')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <h1>Hello World</h1>
      <form className="form" onSubmit={onSubmit}>
        <label htmlFor="name">What is your name (not dani)</label>
        <input
          id="name"
          name="name"
          type="text"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
          required
        />
        <button type="submit" disabled={loading}>
          {loading ? '…' : 'Say hello'}
        </button>
      </form>
      {greeting && <p className="greeting">{greeting}</p>}
      {error && <p className="error">{error}</p>}
    </main>
  )
}
