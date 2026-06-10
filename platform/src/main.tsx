import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { setRuntimeConfig, type RuntimeConfig } from './lib/runtimeConfig'
import { initFirebase } from './lib/firebase'
import { installAuthFetch } from './lib/authedFetch'

// Bootstrap: load the runtime auth config, init Firebase + the token-injecting
// fetch wrapper, THEN render. Defaults to `open` (local dev) if the probe fails.
async function bootstrap() {
  let config: RuntimeConfig = { authMode: 'open', firebase: null }
  try {
    const r = await fetch('/api/config/firebase')
    if (r.ok) config = await r.json()
  } catch {
    /* no backend / offline — stay in open mode */
  }
  setRuntimeConfig(config)
  if (config.authMode === 'firebase' && config.firebase) {
    initFirebase(config.firebase)
  }
  installAuthFetch() // no-op unless firebase mode

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void bootstrap()
