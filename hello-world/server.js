import express from 'express'
import path from 'path'
import { fileURLToPath } from 'url'
import fs from 'fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const PORT = Number(process.env.PORT) || 3000
const distDir = path.join(__dirname, 'dist')
const serveStatic = fs.existsSync(distDir)

const app = express()
app.use(express.json())

app.post('/api/hello', (req, res) => {
  const name = String(req.body?.name ?? '').trim()
  if (!name) {
    return res.status(400).json({ error: 'Name is required' })
  }

  // Intentional crash for CloudWatch testing when name is "dani".
  if (name.toLowerCase() === 'dani') {
    console.error('CRASH_TEST: intentional null dereference for name=dani')
    const boom = null
    // TypeError: Cannot read properties of null (JS equivalent of NPE)
    boom.crash()
  }

  return res.json({ message: `Hello ${name}` })
})

if (serveStatic) {
  app.use(express.static(distDir))
  app.get('/{*splat}', (_req, res) => {
    res.sendFile(path.join(distDir, 'index.html'))
  })
}

app.use((err, _req, res, _next) => {
  console.error(err.stack || err)
  res.status(500).json({ error: 'Internal server error' })
})

app.listen(PORT, () => {
  console.log(
    `hello-world listening on http://127.0.0.1:${PORT}` +
      (serveStatic ? ' (serving dist/)' : ' (API only — use Vite for the UI)'),
  )
})
