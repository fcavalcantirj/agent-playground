import { Code2, Copy } from "lucide-react"

const endpoints = [
  {
    method: "POST",
    path: "/api/agents",
    description: "Create a new agent",
    body: `{
  "name": "my-assistant",
  "clone": "hermes-agent",
  "model": "anthropic/claude-3-sonnet",
  "channels": ["discord", "telegram"],
  "config": {
    "memory": true,
    "maxTokens": 4096
  }
}`,
    response: `{
  "id": "agent_abc123",
  "name": "my-assistant",
  "status": "created",
  "createdAt": "2024-01-15T10:30:00Z"
}`,
  },
  {
    method: "GET",
    path: "/api/agents",
    description: "List all agents",
    params: [
      { name: "status", type: "string", desc: "Filter by status (running, stopped)" },
      { name: "limit", type: "number", desc: "Max results (default: 20)" },
      { name: "offset", type: "number", desc: "Pagination offset" },
    ],
    response: `{
  "agents": [
    {
      "id": "agent_abc123",
      "name": "my-assistant",
      "status": "running",
      "model": "claude-3-sonnet",
      "channels": ["discord"]
    }
  ],
  "total": 1,
  "hasMore": false
}`,
  },
  {
    method: "GET",
    path: "/api/agents/:id",
    description: "Get agent details",
    response: `{
  "id": "agent_abc123",
  "name": "my-assistant",
  "status": "running",
  "clone": "hermes-agent",
  "model": "anthropic/claude-3-sonnet",
  "channels": ["discord", "telegram"],
  "config": {
    "memory": true,
    "maxTokens": 4096,
    "a2aEnabled": true
  },
  "stats": {
    "messagesProcessed": 1523,
    "uptime": 86400
  },
  "createdAt": "2024-01-15T10:30:00Z"
}`,
  },
  {
    method: "POST",
    path: "/api/agents/:id/start",
    description: "Start an agent",
    response: `{
  "id": "agent_abc123",
  "status": "running",
  "startedAt": "2024-01-15T10:30:00Z"
}`,
  },
  {
    method: "POST",
    path: "/api/agents/:id/stop",
    description: "Stop an agent",
    response: `{
  "id": "agent_abc123",
  "status": "stopped",
  "stoppedAt": "2024-01-15T10:30:00Z"
}`,
  },
  {
    method: "POST",
    path: "/api/agents/:id/message",
    description: "Send a message to an agent",
    body: `{
  "content": "Hello, how are you?",
  "userId": "user_123",
  "channel": "api"
}`,
    response: `{
  "id": "msg_xyz789",
  "agentId": "agent_abc123",
  "response": "Hello! I'm doing great...",
  "tokensUsed": 127,
  "latencyMs": 1250
}`,
  },
]

export default function APIPage() {
  return (
    <article className="prose prose-invert max-w-none">
      {/* Header */}
      <div className="not-prose mb-8">
        <div className="mb-4 flex items-center gap-2 text-primary">
          <Code2 className="h-5 w-5" />
          <span className="text-sm font-medium">Reference</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">
          API Reference
        </h1>
        <p className="mt-3 text-lg text-muted-foreground">
          RESTful API for programmatic agent management.
        </p>
      </div>

      {/* Base URL */}
      <h2>Base URL</h2>
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <pre className="p-4"><code className="text-sm">https://api.agentplayground.dev/v1</code></pre>
      </div>

      {/* Authentication */}
      <h2>Authentication</h2>
      <p>All API requests require an API key passed in the Authorization header:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <pre className="p-4"><code className="text-sm">{`Authorization: Bearer your-api-key`}</code></pre>
      </div>

      {/* Endpoints */}
      <h2>Endpoints</h2>
      
      <div className="not-prose space-y-6">
        {endpoints.map((endpoint, i) => (
          <div key={i} className="rounded-xl border border-border/50 bg-card/30 overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-3 border-b border-border/50 bg-muted/20 px-5 py-3">
              <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                endpoint.method === "GET" ? "bg-green-500/20 text-green-400" :
                endpoint.method === "POST" ? "bg-blue-500/20 text-blue-400" :
                endpoint.method === "PUT" ? "bg-yellow-500/20 text-yellow-400" :
                "bg-red-500/20 text-red-400"
              }`}>
                {endpoint.method}
              </span>
              <code className="text-sm text-foreground">{endpoint.path}</code>
            </div>

            <div className="p-5">
              <p className="mb-4 text-sm text-muted-foreground">{endpoint.description}</p>

              {/* Query Params */}
              {endpoint.params && (
                <div className="mb-4">
                  <span className="text-xs font-medium uppercase text-muted-foreground">Query Parameters</span>
                  <div className="mt-2 space-y-2">
                    {endpoint.params.map((param, j) => (
                      <div key={j} className="flex items-start gap-2 text-sm">
                        <code className="text-primary">{param.name}</code>
                        <span className="text-muted-foreground/60">({param.type})</span>
                        <span className="text-muted-foreground">- {param.desc}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Request Body */}
              {endpoint.body && (
                <div className="mb-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium uppercase text-muted-foreground">Request Body</span>
                    <button className="text-muted-foreground hover:text-foreground">
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <pre className="rounded-lg bg-background/50 p-4 text-sm overflow-x-auto">
                    <code>{endpoint.body}</code>
                  </pre>
                </div>
              )}

              {/* Response */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium uppercase text-muted-foreground">Response</span>
                  <button className="text-muted-foreground hover:text-foreground">
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                </div>
                <pre className="rounded-lg bg-background/50 p-4 text-sm overflow-x-auto">
                  <code>{endpoint.response}</code>
                </pre>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Error Codes */}
      <h2>Error Codes</h2>
      <div className="not-prose overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/50">
              <th className="py-3 pr-4 text-left font-medium text-foreground">Code</th>
              <th className="py-3 pr-4 text-left font-medium text-foreground">Status</th>
              <th className="py-3 text-left font-medium text-foreground">Description</th>
            </tr>
          </thead>
          <tbody className="text-muted-foreground">
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono">400</td>
              <td className="py-3 pr-4">Bad Request</td>
              <td className="py-3">Invalid request body or parameters</td>
            </tr>
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono">401</td>
              <td className="py-3 pr-4">Unauthorized</td>
              <td className="py-3">Invalid or missing API key</td>
            </tr>
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono">404</td>
              <td className="py-3 pr-4">Not Found</td>
              <td className="py-3">Agent or resource not found</td>
            </tr>
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono">429</td>
              <td className="py-3 pr-4">Too Many Requests</td>
              <td className="py-3">Rate limit exceeded</td>
            </tr>
            <tr>
              <td className="py-3 pr-4 font-mono">500</td>
              <td className="py-3 pr-4">Internal Error</td>
              <td className="py-3">Server error, please retry</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  )
}
