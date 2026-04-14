"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import {
  Key,
  Plus,
  Copy,
  Eye,
  EyeOff,
  Trash2,
  Check,
  AlertCircle,
  MoreVertical,
} from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

interface ApiKey {
  id: string
  name: string
  key: string
  created: string
  lastUsed: string
  status: "active" | "revoked"
}

const mockKeys: ApiKey[] = [
  {
    id: "1",
    name: "Production Key",
    key: "ap_prod_sk_1234567890abcdefghij",
    created: "Jan 15, 2026",
    lastUsed: "2 hours ago",
    status: "active",
  },
  {
    id: "2",
    name: "Development Key",
    key: "ap_dev_sk_0987654321zyxwvutsrq",
    created: "Feb 3, 2026",
    lastUsed: "5 minutes ago",
    status: "active",
  },
  {
    id: "3",
    name: "Testing Key",
    key: "ap_test_sk_abcdef123456789012",
    created: "Mar 20, 2026",
    lastUsed: "Never",
    status: "revoked",
  },
]

export default function ApiKeysPage() {
  const [keys, setKeys] = useState(mockKeys)
  const [visibleKeys, setVisibleKeys] = useState<string[]>([])
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [newKeyName, setNewKeyName] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)

  const toggleKeyVisibility = (id: string) => {
    setVisibleKeys(prev =>
      prev.includes(id) ? prev.filter(k => k !== id) : [...prev, id]
    )
  }

  const copyKey = async (id: string, key: string) => {
    await navigator.clipboard.writeText(key)
    setCopiedKey(id)
    setTimeout(() => setCopiedKey(null), 2000)
  }

  const createKey = () => {
    const newKey: ApiKey = {
      id: Date.now().toString(),
      name: newKeyName || "New API Key",
      key: `ap_live_sk_${Math.random().toString(36).substr(2, 20)}`,
      created: "Just now",
      lastUsed: "Never",
      status: "active",
    }
    setKeys([newKey, ...keys])
    setNewKeyName("")
    setDialogOpen(false)
  }

  const revokeKey = (id: string) => {
    setKeys(keys.map(key =>
      key.id === id ? { ...key, status: "revoked" as const } : key
    ))
  }

  const deleteKey = (id: string) => {
    setKeys(keys.filter(key => key.id !== id))
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">API Keys</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your API keys for programmatic access
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2 bg-primary text-primary-foreground">
              <Plus className="h-4 w-4" />
              Create Key
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create API Key</DialogTitle>
              <DialogDescription>
                Create a new API key for accessing Agent Playground programmatically.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <label className="mb-1.5 block text-sm text-muted-foreground">Key Name</label>
              <Input
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="e.g., Production, Development"
                className="bg-background/50"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={createKey} className="bg-primary text-primary-foreground">
                Create Key
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Warning */}
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-yellow-500/30 bg-yellow-500/5 p-4">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-yellow-500" />
        <div>
          <p className="text-sm font-medium text-foreground">Keep your API keys secure</p>
          <p className="text-xs text-muted-foreground">
            Never share your API keys or commit them to version control. Use environment variables instead.
          </p>
        </div>
      </div>

      {/* Keys List */}
      <div className="space-y-3">
        {keys.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 py-12 text-center">
            <Key className="mb-3 h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">No API keys yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Create your first API key to get started
            </p>
          </div>
        ) : (
          keys.map((apiKey) => (
            <div
              key={apiKey.id}
              className={cn(
                "rounded-xl border p-4 transition-all sm:p-5",
                apiKey.status === "revoked"
                  ? "border-border/30 bg-muted/20 opacity-60"
                  : "border-border/50 bg-card/30"
              )}
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="font-semibold text-foreground">{apiKey.name}</h3>
                    <span className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      apiKey.status === "active"
                        ? "bg-green-500/20 text-green-400"
                        : "bg-muted text-muted-foreground"
                    )}>
                      {apiKey.status}
                    </span>
                  </div>
                  
                  {/* Key Display */}
                  <div className="flex items-center gap-2">
                    <code className="rounded bg-muted/50 px-2 py-1 font-mono text-xs text-muted-foreground">
                      {visibleKeys.includes(apiKey.id)
                        ? apiKey.key
                        : apiKey.key.substring(0, 12) + "••••••••••••••••"}
                    </code>
                    <button
                      onClick={() => toggleKeyVisibility(apiKey.id)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      {visibleKeys.includes(apiKey.id) ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </button>
                    <button
                      onClick={() => copyKey(apiKey.id, apiKey.key)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      {copiedKey === apiKey.id ? (
                        <Check className="h-4 w-4 text-green-500" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </button>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>Created: {apiKey.created}</span>
                    <span>Last used: {apiKey.lastUsed}</span>
                  </div>
                </div>

                {/* Actions */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {apiKey.status === "active" && (
                      <DropdownMenuItem onClick={() => revokeKey(apiKey.id)}>
                        <AlertCircle className="mr-2 h-4 w-4" />
                        Revoke Key
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onClick={() => deleteKey(apiKey.id)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Usage Info */}
      <div className="mt-8 rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
        <h2 className="mb-3 font-semibold text-foreground">Quick Start</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Use your API key to authenticate requests to the Agent Playground API:
        </p>
        <div className="overflow-x-auto rounded-lg bg-muted/30 p-4">
          <pre className="text-xs text-muted-foreground">
            <code>{`curl -X POST https://api.agentplayground.dev/v1/agents \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"clone": "hermes-agent", "model": "claude-3-sonnet"}'`}</code>
          </pre>
        </div>
      </div>
    </div>
  )
}
