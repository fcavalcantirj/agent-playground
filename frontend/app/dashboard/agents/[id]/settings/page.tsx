"use client"

import { useState, use } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import {
  ArrowLeft,
  Save,
  Trash2,
  AlertTriangle,
  Settings2,
  Bot,
  Zap,
  Shield,
  Bell,
  Globe,
  Key,
} from "lucide-react"

export default function AgentSettingsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()
  
  const [settings, setSettings] = useState({
    name: "Customer Support Bot",
    description: "Handles customer inquiries across Discord and Telegram",
    webhook: "https://api.agentplayground.dev/webhook/abc123",
    apiKey: "sk-agent-xxxxxxxxxxxxxxxxxxxxx",
    rateLimit: 100,
    timeout: 30,
    retries: 3,
    notifications: {
      onError: true,
      onWarning: true,
      onSuccess: false,
      dailyDigest: true,
    },
    security: {
      allowedDomains: "*.example.com, api.partner.com",
      ipWhitelist: "",
      requireAuth: true,
    },
    advanced: {
      debugMode: false,
      logLevel: "info",
      persistLogs: true,
    },
  })

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const handleSave = () => {
    toast.success("Settings saved successfully")
  }

  const handleDelete = () => {
    toast.success("Agent deleted")
    router.push("/dashboard")
  }

  const regenerateApiKey = () => {
    setSettings({
      ...settings,
      apiKey: `sk-agent-${Math.random().toString(36).substring(2, 15)}${Math.random().toString(36).substring(2, 15)}`,
    })
    toast.success("API key regenerated")
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <Link 
          href={`/dashboard/agents/${id}`}
          className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Agent
        </Link>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Agent Settings</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Configure settings for {settings.name}
            </p>
          </div>
          
          <Button onClick={handleSave} className="gap-2">
            <Save className="h-4 w-4" />
            Save Changes
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        {/* General Settings */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">General</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Agent Name</label>
              <Input
                value={settings.name}
                onChange={(e) => setSettings({ ...settings, name: e.target.value })}
                className="bg-background/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Webhook URL</label>
              <Input
                value={settings.webhook}
                readOnly
                className="bg-background/50 font-mono text-xs"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Description</label>
              <textarea
                value={settings.description}
                onChange={(e) => setSettings({ ...settings, description: e.target.value })}
                rows={2}
                className="w-full resize-none rounded-lg border border-border/50 bg-background/50 p-3 text-sm focus:border-primary focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* API & Rate Limiting */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Key className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">API & Rate Limiting</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">API Key</label>
              <div className="flex gap-2">
                <Input
                  value={settings.apiKey}
                  readOnly
                  type="password"
                  className="flex-1 bg-background/50 font-mono text-xs"
                />
                <Button variant="outline" onClick={regenerateApiKey}>
                  Regenerate
                </Button>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Rate Limit (req/min)</label>
              <Input
                type="number"
                value={settings.rateLimit}
                onChange={(e) => setSettings({ ...settings, rateLimit: parseInt(e.target.value) || 100 })}
                className="bg-background/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Timeout (seconds)</label>
              <Input
                type="number"
                value={settings.timeout}
                onChange={(e) => setSettings({ ...settings, timeout: parseInt(e.target.value) || 30 })}
                className="bg-background/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Max Retries</label>
              <Input
                type="number"
                value={settings.retries}
                onChange={(e) => setSettings({ ...settings, retries: parseInt(e.target.value) || 3 })}
                className="bg-background/50"
              />
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Bell className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Notifications</h2>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Error Alerts</p>
                <p className="text-xs text-muted-foreground">Get notified when errors occur</p>
              </div>
              <Switch
                checked={settings.notifications.onError}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  notifications: { ...settings.notifications, onError: v }
                })}
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Warning Alerts</p>
                <p className="text-xs text-muted-foreground">Get notified for warnings</p>
              </div>
              <Switch
                checked={settings.notifications.onWarning}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  notifications: { ...settings.notifications, onWarning: v }
                })}
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Success Notifications</p>
                <p className="text-xs text-muted-foreground">Get notified on successful tasks</p>
              </div>
              <Switch
                checked={settings.notifications.onSuccess}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  notifications: { ...settings.notifications, onSuccess: v }
                })}
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Daily Digest</p>
                <p className="text-xs text-muted-foreground">Receive daily summary email</p>
              </div>
              <Switch
                checked={settings.notifications.dailyDigest}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  notifications: { ...settings.notifications, dailyDigest: v }
                })}
              />
            </div>
          </div>
        </div>

        {/* Security */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Security</h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Allowed Domains (comma-separated)</label>
              <Input
                value={settings.security.allowedDomains}
                onChange={(e) => setSettings({
                  ...settings,
                  security: { ...settings.security, allowedDomains: e.target.value }
                })}
                placeholder="*.example.com, api.partner.com"
                className="bg-background/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">IP Whitelist (comma-separated)</label>
              <Input
                value={settings.security.ipWhitelist}
                onChange={(e) => setSettings({
                  ...settings,
                  security: { ...settings.security, ipWhitelist: e.target.value }
                })}
                placeholder="Leave empty to allow all IPs"
                className="bg-background/50"
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Require Authentication</p>
                <p className="text-xs text-muted-foreground">Require API key for all requests</p>
              </div>
              <Switch
                checked={settings.security.requireAuth}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  security: { ...settings.security, requireAuth: v }
                })}
              />
            </div>
          </div>
        </div>

        {/* Advanced */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Advanced</h2>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Debug Mode</p>
                <p className="text-xs text-muted-foreground">Enable verbose logging</p>
              </div>
              <Switch
                checked={settings.advanced.debugMode}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  advanced: { ...settings.advanced, debugMode: v }
                })}
              />
            </div>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm text-foreground">Persist Logs</p>
                <p className="text-xs text-muted-foreground">Save logs to storage</p>
              </div>
              <Switch
                checked={settings.advanced.persistLogs}
                onCheckedChange={(v) => setSettings({
                  ...settings,
                  advanced: { ...settings.advanced, persistLogs: v }
                })}
              />
            </div>
          </div>
        </div>

        {/* Danger Zone */}
        <div className="rounded-xl border border-destructive/50 bg-destructive/5 p-4 sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <h2 className="font-semibold text-destructive">Danger Zone</h2>
          </div>
          <p className="mb-4 text-sm text-muted-foreground">
            Once you delete an agent, there is no going back. Please be certain.
          </p>
          {!showDeleteConfirm ? (
            <Button 
              variant="destructive" 
              onClick={() => setShowDeleteConfirm(true)}
              className="gap-2"
            >
              <Trash2 className="h-4 w-4" />
              Delete Agent
            </Button>
          ) : (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <p className="text-sm text-destructive">Are you sure? This action cannot be undone.</p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>
                  Cancel
                </Button>
                <Button variant="destructive" onClick={handleDelete}>
                  Yes, Delete Agent
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
