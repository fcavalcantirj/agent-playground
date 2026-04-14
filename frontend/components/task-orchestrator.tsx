"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  Circle,
  Clock,
  AlertCircle,
  ChevronRight,
  Workflow,
  GitBranch,
  Send,
  Loader2
} from "lucide-react"

export interface A2ATask {
  id: string
  name: string
  description: string
  status: "pending" | "running" | "completed" | "failed" | "waiting"
  assignedAgents: string[]
  subtasks: A2ASubtask[]
  artifacts: A2AArtifact[]
  createdAt: Date
  completedAt?: Date
}

export interface A2ASubtask {
  id: string
  name: string
  status: "pending" | "running" | "completed" | "failed"
  agentId: string
  agentName: string
  output?: string
}

export interface A2AArtifact {
  id: string
  name: string
  type: "text" | "code" | "image" | "data"
  content: string
  createdBy: string
}

interface TaskOrchestratorProps {
  tasks: A2ATask[]
  onCreateTask: (task: Partial<A2ATask>) => void
  onCancelTask: (taskId: string) => void
  agents: { id: string; name: string; isRunning: boolean }[]
}

export function TaskOrchestrator({ tasks, onCreateTask, onCancelTask, agents }: TaskOrchestratorProps) {
  const [newTaskName, setNewTaskName] = useState("")
  const [newTaskDescription, setNewTaskDescription] = useState("")
  const [selectedAgents, setSelectedAgents] = useState<string[]>([])
  const [expandedTask, setExpandedTask] = useState<string | null>(null)

  const runningAgents = agents.filter(a => a.isRunning)

  const handleCreateTask = () => {
    if (!newTaskName.trim() || selectedAgents.length === 0) return
    
    onCreateTask({
      name: newTaskName,
      description: newTaskDescription,
      assignedAgents: selectedAgents,
      subtasks: [],
      artifacts: []
    })
    
    setNewTaskName("")
    setNewTaskDescription("")
    setSelectedAgents([])
  }

  const toggleAgent = (agentId: string) => {
    setSelectedAgents(prev =>
      prev.includes(agentId)
        ? prev.filter(id => id !== agentId)
        : [...prev, agentId]
    )
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "pending": return <Circle className="w-4 h-4 text-muted-foreground" />
      case "running": return <Loader2 className="w-4 h-4 text-primary animate-spin" />
      case "completed": return <CheckCircle2 className="w-4 h-4 text-green-500" />
      case "failed": return <AlertCircle className="w-4 h-4 text-red-500" />
      case "waiting": return <Clock className="w-4 h-4 text-yellow-500" />
      default: return <Circle className="w-4 h-4 text-muted-foreground" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "pending": return "bg-muted text-muted-foreground"
      case "running": return "bg-primary/20 text-primary"
      case "completed": return "bg-green-500/20 text-green-400"
      case "failed": return "bg-red-500/20 text-red-400"
      case "waiting": return "bg-yellow-500/20 text-yellow-400"
      default: return "bg-muted text-muted-foreground"
    }
  }

  return (
    <div className="space-y-4">
      <Tabs defaultValue="tasks" className="w-full">
        <TabsList className="w-full bg-muted/50 p-1">
          <TabsTrigger value="tasks" className="flex-1 text-sm">
            <Workflow className="w-4 h-4 mr-2" />
            Tasks
          </TabsTrigger>
          <TabsTrigger value="create" className="flex-1 text-sm">
            <Send className="w-4 h-4 mr-2" />
            Create Task
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="mt-4">
          <ScrollArea className="h-[400px]">
            {tasks.length === 0 ? (
              <div className="text-center py-12">
                <GitBranch className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                <p className="text-muted-foreground">No collaborative tasks yet</p>
                <p className="text-muted-foreground/70 text-sm mt-1">
                  Create a task to orchestrate multiple agents
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {tasks.map(task => (
                  <div
                    key={task.id}
                    className="rounded-xl border border-border/50 bg-card/50 overflow-hidden"
                  >
                    {/* Task Header */}
                    <button
                      onClick={() => setExpandedTask(expandedTask === task.id ? null : task.id)}
                      className="w-full p-4 flex items-center gap-4 hover:bg-muted/30 transition-colors text-left"
                    >
                      <ChevronRight className={cn(
                        "w-4 h-4 text-muted-foreground transition-transform",
                        expandedTask === task.id && "rotate-90"
                      )} />
                      
                      {getStatusIcon(task.status)}
                      
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-foreground truncate">{task.name}</h4>
                        <p className="text-xs text-muted-foreground truncate">{task.description}</p>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "px-2 py-0.5 rounded-full text-xs",
                          getStatusColor(task.status)
                        )}>
                          {task.status}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {task.assignedAgents.length} agents
                        </span>
                      </div>
                    </button>

                    {/* Expanded Content */}
                    {expandedTask === task.id && (
                      <div className="border-t border-border/50 p-4 space-y-4">
                        {/* Subtasks */}
                        <div>
                          <h5 className="text-sm font-medium text-foreground mb-2">Subtasks</h5>
                          {task.subtasks.length === 0 ? (
                            <p className="text-sm text-muted-foreground">Processing...</p>
                          ) : (
                            <div className="space-y-2">
                              {task.subtasks.map(subtask => (
                                <div
                                  key={subtask.id}
                                  className="flex items-start gap-3 p-2 rounded-lg bg-background/50"
                                >
                                  {getStatusIcon(subtask.status)}
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm text-foreground">{subtask.name}</span>
                                      <span className="text-xs text-muted-foreground">
                                        by {subtask.agentName}
                                      </span>
                                    </div>
                                    {subtask.output && (
                                      <p className="text-xs text-muted-foreground mt-1 truncate">
                                        {subtask.output}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Artifacts */}
                        {task.artifacts.length > 0 && (
                          <div>
                            <h5 className="text-sm font-medium text-foreground mb-2">Artifacts</h5>
                            <div className="space-y-2">
                              {task.artifacts.map(artifact => (
                                <div
                                  key={artifact.id}
                                  className="p-3 rounded-lg bg-background/50 border border-border/30"
                                >
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-medium text-foreground">
                                      {artifact.name}
                                    </span>
                                    <span className={cn(
                                      "px-2 py-0.5 rounded text-xs",
                                      artifact.type === "code" && "bg-blue-500/20 text-blue-400",
                                      artifact.type === "text" && "bg-green-500/20 text-green-400",
                                      artifact.type === "data" && "bg-purple-500/20 text-purple-400",
                                      artifact.type === "image" && "bg-yellow-500/20 text-yellow-400"
                                    )}>
                                      {artifact.type}
                                    </span>
                                  </div>
                                  <pre className="text-xs text-muted-foreground bg-background/50 p-2 rounded overflow-x-auto">
                                    {artifact.content.slice(0, 200)}
                                    {artifact.content.length > 200 && "..."}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Actions */}
                        <div className="flex items-center gap-2 pt-2 border-t border-border/30">
                          {task.status === "running" ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => onCancelTask(task.id)}
                              className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            >
                              <Pause className="w-3 h-3 mr-1" />
                              Cancel
                            </Button>
                          ) : task.status === "failed" ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-primary hover:text-primary/80"
                            >
                              <RotateCcw className="w-3 h-3 mr-1" />
                              Retry
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="create" className="mt-4">
          <div className="p-4 rounded-xl border border-border/50 bg-card/50 space-y-4">
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Task Name</label>
              <Input
                value={newTaskName}
                onChange={(e) => setNewTaskName(e.target.value)}
                placeholder="e.g., Analyze and summarize data"
                className="bg-background/50"
              />
            </div>

            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Description</label>
              <textarea
                value={newTaskDescription}
                onChange={(e) => setNewTaskDescription(e.target.value)}
                placeholder="Describe what the agents should accomplish together..."
                className="w-full h-24 px-3 py-2 rounded-lg border border-border/50 bg-background/50 text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>

            <div>
              <label className="text-sm text-muted-foreground mb-2 block">
                Assign Agents ({selectedAgents.length} selected)
              </label>
              {runningAgents.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No running agents. Deploy agents first.
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {runningAgents.map(agent => (
                    <button
                      key={agent.id}
                      onClick={() => toggleAgent(agent.id)}
                      className={cn(
                        "p-3 rounded-lg border transition-all text-left",
                        selectedAgents.includes(agent.id)
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border/50 text-muted-foreground hover:border-primary/50"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <div className={cn(
                          "w-2 h-2 rounded-full",
                          selectedAgents.includes(agent.id) ? "bg-primary" : "bg-green-500"
                        )} />
                        <span className="text-sm font-medium">{agent.name}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <Button
              onClick={handleCreateTask}
              disabled={!newTaskName.trim() || selectedAgents.length === 0}
              className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90"
            >
              <Play className="w-4 h-4 mr-2" />
              Create Collaborative Task
            </Button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
