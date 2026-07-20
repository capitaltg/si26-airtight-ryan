import { useQuery } from "@tanstack/react-query"

async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch("/api/health")
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  })

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 text-slate-900">
      <h1 className="text-3xl font-semibold">Airtight</h1>
      <p className="text-slate-500">Federal-orals rehearsal — POC scaffold</p>
      <div className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm shadow-sm">
        API health:{" "}
        {isLoading ? (
          <span className="text-slate-500">checking…</span>
        ) : isError ? (
          <span className="font-medium text-red-700">unreachable</span>
        ) : (
          <span className="font-medium text-green-700">{data?.status}</span>
        )}
      </div>
    </main>
  )
}
