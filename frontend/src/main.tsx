import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import Landing from './pages/Landing.tsx'

// Two-surface routing without a router: "/" is the marketing front door,
// "/app" (and any deep path) is the workspace. vercel.json rewrites all
// paths to index.html so direct loads of /app work in production.
const isWorkspace = window.location.pathname.startsWith('/app')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isWorkspace ? <App /> : <Landing />}
  </StrictMode>,
)
