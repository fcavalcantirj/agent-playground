"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Bell,
  Check,
  CheckCheck,
  AlertTriangle,
  Info,
  Zap,
  MessageSquare,
  Settings,
  Trash2,
} from "lucide-react"

type NotificationType = "info" | "warning" | "success" | "message"

interface Notification {
  id: string
  type: NotificationType
  title: string
  message: string
  time: string
  read: boolean
  agentName?: string
}

const mockNotifications: Notification[] = [
  {
    id: "1",
    type: "success",
    title: "Agent deployed successfully",
    message: "Your Customer Support Bot is now live and ready to receive messages.",
    time: "5 minutes ago",
    read: false,
    agentName: "Customer Support Bot",
  },
  {
    id: "2",
    type: "warning",
    title: "High usage detected",
    message: "You've used 80% of your monthly message quota. Consider upgrading your plan.",
    time: "2 hours ago",
    read: false,
  },
  {
    id: "3",
    type: "message",
    title: "New conversation started",
    message: "A user started a new conversation with Code Assistant via Discord.",
    time: "4 hours ago",
    read: true,
    agentName: "Code Assistant",
  },
  {
    id: "4",
    type: "info",
    title: "New feature available",
    message: "A2A Protocol support is now available for all agents. Enable it in settings.",
    time: "1 day ago",
    read: true,
  },
  {
    id: "5",
    type: "success",
    title: "Weekly report ready",
    message: "Your weekly analytics report for all agents is now available.",
    time: "2 days ago",
    read: true,
  },
  {
    id: "6",
    type: "warning",
    title: "API rate limit approaching",
    message: "Research Agent is approaching the rate limit. Consider optimizing requests.",
    time: "3 days ago",
    read: true,
    agentName: "Research Agent",
  },
]

const typeIcons: Record<NotificationType, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  success: Zap,
  message: MessageSquare,
}

const typeColors: Record<NotificationType, string> = {
  info: "text-blue-500 bg-blue-500/10",
  warning: "text-yellow-500 bg-yellow-500/10",
  success: "text-green-500 bg-green-500/10",
  message: "text-primary bg-primary/10",
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState(mockNotifications)
  const [filter, setFilter] = useState<"all" | "unread">("all")

  const unreadCount = notifications.filter(n => !n.read).length
  const filteredNotifications = filter === "all"
    ? notifications
    : notifications.filter(n => !n.read)

  const markAsRead = (id: string) => {
    setNotifications(notifications.map(n =>
      n.id === id ? { ...n, read: true } : n
    ))
  }

  const markAllAsRead = () => {
    setNotifications(notifications.map(n => ({ ...n, read: true })))
  }

  const deleteNotification = (id: string) => {
    setNotifications(notifications.filter(n => n.id !== id))
  }

  const clearAll = () => {
    setNotifications([])
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Notifications</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {unreadCount > 0 ? `You have ${unreadCount} unread notification${unreadCount > 1 ? "s" : ""}` : "All caught up!"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={markAllAsRead}
            disabled={unreadCount === 0}
            className="gap-1.5"
          >
            <CheckCheck className="h-4 w-4" />
            <span className="hidden sm:inline">Mark all read</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={clearAll}
            disabled={notifications.length === 0}
            className="gap-1.5 text-destructive hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
            <span className="hidden sm:inline">Clear all</span>
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex gap-2 sm:mb-6">
        {(["all", "unread"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              filter === f
                ? "bg-primary text-primary-foreground"
                : "bg-muted/50 text-muted-foreground hover:bg-muted"
            )}
          >
            {f === "all" ? "All" : `Unread (${unreadCount})`}
          </button>
        ))}
      </div>

      {/* Notifications List */}
      <div className="space-y-3">
        {filteredNotifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 py-12 text-center">
            <Bell className="mb-3 h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              {filter === "unread" ? "No unread notifications" : "No notifications yet"}
            </p>
          </div>
        ) : (
          filteredNotifications.map((notification) => {
            const Icon = typeIcons[notification.type]
            return (
              <div
                key={notification.id}
                className={cn(
                  "group relative rounded-xl border p-4 transition-all sm:p-5",
                  notification.read
                    ? "border-border/30 bg-card/20"
                    : "border-primary/30 bg-primary/5"
                )}
              >
                {/* Unread indicator */}
                {!notification.read && (
                  <div className="absolute left-3 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-primary" />
                )}

                <div className="flex gap-3 sm:gap-4">
                  {/* Icon */}
                  <div className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                    typeColors[notification.type]
                  )}>
                    <Icon className="h-5 w-5" />
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-start justify-between gap-2">
                      <h3 className={cn(
                        "text-sm",
                        notification.read ? "text-foreground" : "font-semibold text-foreground"
                      )}>
                        {notification.title}
                      </h3>
                      <span className="shrink-0 text-[10px] text-muted-foreground sm:text-xs">
                        {notification.time}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground sm:text-sm">
                      {notification.message}
                    </p>
                    {notification.agentName && (
                      <span className="mt-2 inline-block rounded bg-muted/50 px-2 py-0.5 text-[10px] text-muted-foreground">
                        {notification.agentName}
                      </span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-start gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    {!notification.read && (
                      <button
                        onClick={() => markAsRead(notification.id)}
                        className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                        title="Mark as read"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => deleteNotification(notification.id)}
                      className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Notification Settings Link */}
      <div className="mt-8 flex items-center justify-center">
        <Button variant="ghost" className="gap-2 text-muted-foreground" asChild>
          <a href="/dashboard/settings">
            <Settings className="h-4 w-4" />
            Notification Settings
          </a>
        </Button>
      </div>
    </div>
  )
}
