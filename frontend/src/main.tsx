import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import Landing from './pages/Landing.tsx'
import IdeaStream from './pages/IdeaStream.tsx'

// Three-surface routing without a router: "/" is the marketing front door,
// "/ideas" is the trend think-tank, "/app" (and deep paths) is the workspace.
// vercel.json rewrites all paths to index.html so direct loads work in prod.
const path = window.location.pathname
const Page = path.startsWith('/app') ? App : path.startsWith('/ideas') ? IdeaStream : Landing

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
)
