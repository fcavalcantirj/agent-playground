"use client"

import { useState, useMemo } from "react"
import { cn } from "@/lib/utils"
import { 
  Search, 
  Sparkles, 
  Zap, 
  DollarSign,
  Clock,
  Brain,
  ChevronDown,
  Check,
  Star
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"

export interface OpenRouterModel {
  id: string
  name: string
  provider: string
  contextLength: number
  pricing: {
    prompt: number
    completion: number
  }
  capabilities: ("chat" | "vision" | "function" | "reasoning")[]
  isPopular?: boolean
  isFree?: boolean
}

// OpenRouter models data
export const openRouterModels: OpenRouterModel[] = [
  {
    id: "anthropic/claude-3.5-sonnet",
    name: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    contextLength: 200000,
    pricing: { prompt: 3, completion: 15 },
    capabilities: ["chat", "vision", "function", "reasoning"],
    isPopular: true
  },
  {
    id: "openai/gpt-4-turbo",
    name: "GPT-4 Turbo",
    provider: "OpenAI",
    contextLength: 128000,
    pricing: { prompt: 10, completion: 30 },
    capabilities: ["chat", "vision", "function"],
    isPopular: true
  },
  {
    id: "google/gemini-pro-1.5",
    name: "Gemini Pro 1.5",
    provider: "Google",
    contextLength: 1000000,
    pricing: { prompt: 2.5, completion: 7.5 },
    capabilities: ["chat", "vision", "function"],
    isPopular: true
  },
  {
    id: "meta-llama/llama-3.1-405b-instruct",
    name: "Llama 3.1 405B",
    provider: "Meta",
    contextLength: 131072,
    pricing: { prompt: 2.7, completion: 2.7 },
    capabilities: ["chat", "function"],
    isPopular: true
  },
  {
    id: "mistralai/mixtral-8x22b-instruct",
    name: "Mixtral 8x22B",
    provider: "Mistral",
    contextLength: 65536,
    pricing: { prompt: 0.9, completion: 0.9 },
    capabilities: ["chat", "function"]
  },
  {
    id: "anthropic/claude-3-opus",
    name: "Claude 3 Opus",
    provider: "Anthropic",
    contextLength: 200000,
    pricing: { prompt: 15, completion: 75 },
    capabilities: ["chat", "vision", "function", "reasoning"]
  },
  {
    id: "openai/gpt-4o",
    name: "GPT-4o",
    provider: "OpenAI",
    contextLength: 128000,
    pricing: { prompt: 5, completion: 15 },
    capabilities: ["chat", "vision", "function"],
    isPopular: true
  },
  {
    id: "deepseek/deepseek-chat",
    name: "DeepSeek Chat",
    provider: "DeepSeek",
    contextLength: 64000,
    pricing: { prompt: 0.14, completion: 0.28 },
    capabilities: ["chat", "function"]
  },
  {
    id: "qwen/qwen-2.5-72b-instruct",
    name: "Qwen 2.5 72B",
    provider: "Alibaba",
    contextLength: 131072,
    pricing: { prompt: 0.35, completion: 0.4 },
    capabilities: ["chat", "function"]
  },
  {
    id: "nousresearch/hermes-3-llama-3.1-405b",
    name: "Hermes 3 405B",
    provider: "Nous Research",
    contextLength: 131072,
    pricing: { prompt: 4, completion: 4 },
    capabilities: ["chat", "function", "reasoning"],
    isPopular: true
  },
  {
    id: "cohere/command-r-plus",
    name: "Command R+",
    provider: "Cohere",
    contextLength: 128000,
    pricing: { prompt: 2.5, completion: 10 },
    capabilities: ["chat", "function"]
  },
  {
    id: "perplexity/llama-3.1-sonar-huge-128k-online",
    name: "Sonar Huge 128K",
    provider: "Perplexity",
    contextLength: 127072,
    pricing: { prompt: 5, completion: 5 },
    capabilities: ["chat"]
  },
  {
    id: "meta-llama/llama-3.2-90b-vision-instruct",
    name: "Llama 3.2 90B Vision",
    provider: "Meta",
    contextLength: 131072,
    pricing: { prompt: 0.9, completion: 0.9 },
    capabilities: ["chat", "vision"]
  },
  {
    id: "openai/o1-preview",
    name: "o1-preview",
    provider: "OpenAI",
    contextLength: 128000,
    pricing: { prompt: 15, completion: 60 },
    capabilities: ["chat", "reasoning"],
    isPopular: true
  },
  {
    id: "mistralai/mistral-large",
    name: "Mistral Large",
    provider: "Mistral",
    contextLength: 128000,
    pricing: { prompt: 2, completion: 6 },
    capabilities: ["chat", "function"]
  },
  {
    id: "google/gemma-2-27b-it",
    name: "Gemma 2 27B",
    provider: "Google",
    contextLength: 8192,
    pricing: { prompt: 0.27, completion: 0.27 },
    capabilities: ["chat"],
    isFree: false
  }
]

const providerColors: Record<string, string> = {
  "Anthropic": "text-orange-400",
  "OpenAI": "text-green-400",
  "Google": "text-blue-400",
  "Meta": "text-indigo-400",
  "Mistral": "text-purple-400",
  "DeepSeek": "text-cyan-400",
  "Alibaba": "text-red-400",
  "Nous Research": "text-amber-400",
  "Cohere": "text-pink-400",
  "Perplexity": "text-teal-400",
}

interface ModelSelectorProps {
  selectedModel: OpenRouterModel | null
  onSelectModel: (model: OpenRouterModel) => void
  className?: string
}

export function ModelSelector({ selectedModel, onSelectModel, className }: ModelSelectorProps) {
  const [searchQuery, setSearchQuery] = useState("")
  const [isOpen, setIsOpen] = useState(false)
  const [filterCapability, setFilterCapability] = useState<string | null>(null)

  const filteredModels = useMemo(() => {
    return openRouterModels.filter(model => {
      const matchesSearch = 
        model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        model.provider.toLowerCase().includes(searchQuery.toLowerCase()) ||
        model.id.toLowerCase().includes(searchQuery.toLowerCase())
      
      const matchesCapability = !filterCapability || model.capabilities.includes(filterCapability as typeof model.capabilities[number])
      
      return matchesSearch && matchesCapability
    })
  }, [searchQuery, filterCapability])

  const capabilities = ["chat", "vision", "function", "reasoning"]

  return (
    <div className={cn("relative", className)}>
      {/* Selected Model Display / Trigger */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex w-full items-center justify-between rounded-xl border p-2.5 transition-all duration-300 sm:p-3",
          "bg-card/50 backdrop-blur-sm",
          isOpen ? "border-primary shadow-[0_0_20px_rgba(249,115,22,0.2)]" : "border-border/50 hover:border-primary/50"
        )}
      >
        {selectedModel ? (
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-accent/20 sm:h-8 sm:w-8">
              <Brain className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
            </div>
            <div className="min-w-0 text-left">
              <div className="truncate text-xs font-medium text-foreground sm:text-sm">{selectedModel.name}</div>
              <div className={cn("text-[10px] sm:text-xs", providerColors[selectedModel.provider] || "text-muted-foreground")}>
                {selectedModel.provider}
              </div>
            </div>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground sm:text-sm">Select a model...</span>
        )}
        <ChevronDown className={cn(
          "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 sm:h-4 sm:w-4",
          isOpen && "rotate-180"
        )} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-border/50 bg-card/95 shadow-2xl backdrop-blur-xl">
          {/* Search */}
          <div className="border-b border-border/50 p-2.5 sm:p-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground sm:left-3 sm:h-4 sm:w-4" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search models..."
                className="h-8 border-border/50 bg-background/50 pl-8 text-xs sm:h-9 sm:pl-9 sm:text-sm"
              />
            </div>
            
            {/* Capability filters */}
            <div className="mt-2 flex flex-wrap gap-1.5 sm:gap-2">
              {capabilities.map(cap => (
                <button
                  key={cap}
                  onClick={() => setFilterCapability(filterCapability === cap ? null : cap)}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] transition-all sm:px-2.5 sm:py-1 sm:text-xs",
                    filterCapability === cap 
                      ? "bg-primary text-primary-foreground" 
                      : "bg-muted/50 text-muted-foreground hover:bg-muted"
                  )}
                >
                  {cap}
                </button>
              ))}
            </div>
          </div>

          {/* Models List */}
          <ScrollArea className="h-48 sm:h-64">
            <div className="p-1.5 sm:p-2">
              {filteredModels.map(model => (
                <button
                  key={model.id}
                  onClick={() => {
                    onSelectModel(model)
                    setIsOpen(false)
                  }}
                  className={cn(
                    "w-full rounded-lg p-2.5 text-left transition-all duration-200 sm:p-3",
                    "hover:bg-muted/50",
                    selectedModel?.id === model.id && "bg-primary/10"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 sm:gap-2">
                        <span className="truncate text-xs font-medium text-foreground sm:text-sm">{model.name}</span>
                        {model.isPopular && (
                          <Star className="h-2.5 w-2.5 shrink-0 fill-yellow-500 text-yellow-500 sm:h-3 sm:w-3" />
                        )}
                        {selectedModel?.id === model.id && (
                          <Check className="h-2.5 w-2.5 shrink-0 text-primary sm:h-3 sm:w-3" />
                        )}
                      </div>
                      <span className={cn("text-[10px] sm:text-xs", providerColors[model.provider] || "text-muted-foreground")}>
                        {model.provider}
                      </span>
                    </div>
                    
                    <div className="shrink-0 text-right text-[10px] text-muted-foreground sm:text-xs">
                      <div className="flex items-center justify-end gap-0.5 sm:gap-1">
                        <Clock className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        {(model.contextLength / 1000).toFixed(0)}K
                      </div>
                      <div className="flex items-center justify-end gap-0.5 sm:gap-1">
                        <DollarSign className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        ${model.pricing.prompt}/M
                      </div>
                    </div>
                  </div>
                  
                  {/* Capabilities */}
                  <div className="mt-1.5 flex flex-wrap gap-1 sm:mt-2">
                    {model.capabilities.map(cap => (
                      <span key={cap} className="rounded bg-muted/50 px-1 py-0.5 text-[8px] text-muted-foreground sm:px-1.5 sm:text-[10px]">
                        {cap}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>

          {/* OpenRouter branding */}
          <div className="flex items-center justify-center gap-1.5 border-t border-border/50 p-2 text-[10px] text-muted-foreground sm:gap-2 sm:text-xs">
            <Sparkles className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            Powered by OpenRouter
          </div>
        </div>
      )}
    </div>
  )
}
