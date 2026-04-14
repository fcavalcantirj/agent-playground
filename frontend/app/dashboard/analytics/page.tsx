"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  MessageSquare,
  Clock,
  Users,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react"

const timeRanges = ["24h", "7d", "30d", "90d"]

const stats = [
  {
    title: "Total Messages",
    value: "24,521",
    change: "+12.5%",
    trend: "up",
    icon: MessageSquare,
  },
  {
    title: "Avg Response Time",
    value: "1.2s",
    change: "-8.3%",
    trend: "down",
    icon: Clock,
  },
  {
    title: "Active Users",
    value: "1,847",
    change: "+23.1%",
    trend: "up",
    icon: Users,
  },
  {
    title: "API Calls",
    value: "89,234",
    change: "+5.7%",
    trend: "up",
    icon: Zap,
  },
]

const agentStats = [
  { name: "Customer Support Bot", messages: 8234, successRate: 94.2 },
  { name: "Code Assistant", messages: 6521, successRate: 97.8 },
  { name: "Data Analyst", messages: 5432, successRate: 91.5 },
  { name: "Research Agent", messages: 4334, successRate: 89.3 },
]

const hourlyData = [
  { hour: "00:00", messages: 120 },
  { hour: "04:00", messages: 85 },
  { hour: "08:00", messages: 340 },
  { hour: "12:00", messages: 520 },
  { hour: "16:00", messages: 680 },
  { hour: "20:00", messages: 420 },
]

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState("7d")

  const maxMessages = Math.max(...hourlyData.map(d => d.messages))

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Analytics</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Monitor your agent performance and usage
          </p>
        </div>
        <div className="flex gap-1 rounded-lg bg-muted/50 p-1">
          {timeRanges.map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                timeRange === range
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="mb-6 grid gap-4 sm:mb-8 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.title}
            className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-5"
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <stat.icon className="h-5 w-5 text-primary" />
              </div>
              <div className={cn(
                "flex items-center gap-1 text-xs font-medium",
                stat.trend === "up" ? "text-green-500" : "text-red-500"
              )}>
                {stat.trend === "up" ? (
                  <ArrowUpRight className="h-3 w-3" />
                ) : (
                  <ArrowDownRight className="h-3 w-3" />
                )}
                {stat.change}
              </div>
            </div>
            <p className="text-2xl font-bold text-foreground">{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.title}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Messages Chart */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-foreground">Messages Over Time</h2>
            <BarChart3 className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="flex h-48 items-end gap-2 sm:gap-3">
            {hourlyData.map((data) => (
              <div key={data.hour} className="flex flex-1 flex-col items-center gap-2">
                <div
                  className="w-full rounded-t bg-gradient-to-t from-primary to-primary/50 transition-all hover:from-primary/90"
                  style={{ height: `${(data.messages / maxMessages) * 100}%` }}
                />
                <span className="text-[10px] text-muted-foreground sm:text-xs">{data.hour}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Agent Performance */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-foreground">Agent Performance</h2>
            <TrendingUp className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="space-y-4">
            {agentStats.map((agent) => (
              <div key={agent.name}>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="truncate text-foreground">{agent.name}</span>
                  <span className="shrink-0 text-muted-foreground">
                    {agent.messages.toLocaleString()} msgs
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted/50">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
                      style={{ width: `${agent.successRate}%` }}
                    />
                  </div>
                  <span className="w-12 text-right text-xs text-muted-foreground">
                    {agent.successRate}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="mt-6 rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
        <h2 className="mb-4 font-semibold text-foreground">Usage Breakdown</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">Peak Hours</p>
            <p className="mt-1 text-lg font-semibold text-foreground">2PM - 6PM</p>
            <p className="text-xs text-muted-foreground">Most active period</p>
          </div>
          <div className="rounded-lg bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">Avg Session Length</p>
            <p className="mt-1 text-lg font-semibold text-foreground">8.5 min</p>
            <p className="text-xs text-green-500">+15% from last week</p>
          </div>
          <div className="rounded-lg bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">User Satisfaction</p>
            <p className="mt-1 text-lg font-semibold text-foreground">4.7/5.0</p>
            <p className="text-xs text-muted-foreground">Based on 523 ratings</p>
          </div>
        </div>
      </div>
    </div>
  )
}
