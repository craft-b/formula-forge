import { useState } from "react"
import { Button } from "@/components/ui/button"

const API_URL = import.meta.env.VITE_API_URL

function App() {
  const [input, setInput] = useState("")
  const [response, setResponse] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)

  async function handleSend() {
    if (!input.trim()) return
    setLoading(true)
    setResponse(null)
    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input, session_id: sessionId }),
      })
      const data = await res.json()
      console.log("API response:", data)
      setSessionId(data.session_id)
      setResponse(data.response)
    } catch (err) {
      console.error("API error:", err)
      setResponse("Error — check console.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="font-semibold text-lg text-slate-900">FormulaForge</div>
          <div className="text-sm text-slate-500">In active development</div>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto px-6 py-20 w-full">
        <div className="max-w-3xl">
          <div className="inline-block px-3 py-1 mb-6 text-xs font-medium text-slate-600 bg-slate-100 rounded-full">
            Week 1 · Building
          </div>
          <h1 className="text-5xl font-bold text-slate-900 tracking-tight mb-6">
            Agentic AI for specialized food R&D.
          </h1>
          <p className="text-xl text-slate-600 leading-relaxed mb-8">
            A multi-agent system that compresses early-stage R&D scoping for clinical and medical food — renal-diet, dysphagia-safe, oncology-targeted, and post-surgical formulations.
          </p>
          <div className="flex gap-3">
            <Button asChild>
              <a href="https://github.com/craft-b/formulaforge" target="_blank" rel="noreferrer">
                View on GitHub
              </a>
            </Button>
            <Button variant="outline">Read the build journal</Button>
          </div>
        </div>

        <div className="mt-20 max-w-3xl">
          <div className="p-6 bg-white border border-slate-200 rounded-lg">
            <p className="text-sm font-medium text-slate-500 mb-3">API connection test</p>
            <div className="flex gap-2">
              <input
                className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-slate-400"
                placeholder="Send a message to the backend..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
              />
              <Button onClick={handleSend} disabled={loading}>
                {loading ? "Sending…" : "Send"}
              </Button>
            </div>
            {response && (
              <p className="mt-3 text-sm text-slate-700 bg-slate-50 px-3 py-2 rounded-md border border-slate-100">
                {response}
              </p>
            )}
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl">
          <div className="p-6 bg-white border border-slate-200 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-2">Status</div>
            <div className="text-2xl font-semibold text-slate-900">Week 1 of 8</div>
          </div>
          <div className="p-6 bg-white border border-slate-200 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-2">Architecture</div>
            <div className="text-2xl font-semibold text-slate-900">5 agents</div>
          </div>
          <div className="p-6 bg-white border border-slate-200 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-2">Stack</div>
            <div className="text-2xl font-semibold text-slate-900">LangGraph</div>
          </div>
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white mt-20">
        <div className="max-w-6xl mx-auto px-6 py-6 text-sm text-slate-500">
          Built in public — 8 weeks, $0 budget, personal accounts.
        </div>
      </footer>
    </div>
  )
}

export default App
