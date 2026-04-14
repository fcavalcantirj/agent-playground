"use client"

import { Brain, Zap, Eye, Wrench, Sparkles, DollarSign } from "lucide-react"
import { cn } from "@/lib/utils"

const modelCategories = [
  {
    name: "Flagship Models",
    description: "Best-in-class performance for complex tasks",
    models: [
      { name: "Claude 3.5 Sonnet", provider: "Anthropic", context: "200K", pricing: "$3/M", capabilities: ["chat", "vision", "tools"] },
      { name: "GPT-4 Turbo", provider: "OpenAI", context: "128K", pricing: "$10/M", capabilities: ["chat", "vision", "tools"] },
      { name: "Claude 3 Opus", provider: "Anthropic", context: "200K", pricing: "$15/M", capabilities: ["chat", "vision", "tools", "reasoning"] },
      { name: "Gemini Pro 1.5", provider: "Google", context: "1M", pricing: "$7/M", capabilities: ["chat", "vision", "tools"] },
    ],
  },
  {
    name: "Fast & Efficient",
    description: "Optimized for speed and cost",
    models: [
      { name: "Claude 3 Haiku", provider: "Anthropic", context: "200K", pricing: "$0.25/M", capabilities: ["chat", "tools"] },
      { name: "GPT-4o Mini", provider: "OpenAI", context: "128K", pricing: "$0.15/M", capabilities: ["chat", "vision", "tools"] },
      { name: "Gemini Flash 1.5", provider: "Google", context: "1M", pricing: "$0.35/M", capabilities: ["chat", "vision"] },
      { name: "Llama 3.1 8B", provider: "Meta", context: "128K", pricing: "$0.05/M", capabilities: ["chat"] },
    ],
  },
  {
    name: "Open Source",
    description: "Community-driven models",
    models: [
      { name: "Llama 3.1 70B", provider: "Meta", context: "128K", pricing: "$0.88/M", capabilities: ["chat", "tools"] },
      { name: "Hermes 3 70B", provider: "Nous Research", context: "128K", pricing: "$0.88/M", capabilities: ["chat", "tools", "reasoning"] },
      { name: "Mixtral 8x22B", provider: "Mistral", context: "65K", pricing: "$0.65/M", capabilities: ["chat", "tools"] },
      { name: "Qwen 2.5 72B", provider: "Alibaba", context: "128K", pricing: "$0.75/M", capabilities: ["chat", "tools"] },
    ],
  },
]

const capabilityIcons: Record<string, typeof Brain> = {
  chat: Brain,
  vision: Eye,
  tools: Wrench,
  reasoning: Sparkles,
}

const capabilityColors: Record<string, string> = {
  chat: "bg-blue-500/20 text-blue-400",
  vision: "bg-purple-500/20 text-purple-400",
  tools: "bg-green-500/20 text-green-400",
  reasoning: "bg-yellow-500/20 text-yellow-400",
}

export default function ModelsPage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">Models</h1>
        <p className="mt-3 text-muted-foreground">
          Agent Playground supports any model available through OpenRouter.
        </p>
      </div>

      {/* OpenRouter Integration */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">OpenRouter Integration</h2>
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-5">
          <div className="flex items-start gap-3">
            <Zap className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <h3 className="font-medium text-foreground">Access 100+ Models</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Through our OpenRouter integration, you have access to models from OpenAI, Anthropic, 
                Google, Meta, Mistral, and many more providers - all through a single API.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Capabilities Legend */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Model Capabilities</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(capabilityIcons).map(([cap, Icon]) => (
            <div key={cap} className="flex items-center gap-2 rounded-lg border border-border/50 bg-card/30 p-3">
              <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", capabilityColors[cap])}>
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-medium capitalize text-foreground">{cap}</p>
                <p className="text-xs text-muted-foreground">
                  {cap === "chat" && "Text generation and conversation"}
                  {cap === "vision" && "Image understanding"}
                  {cap === "tools" && "Function calling support"}
                  {cap === "reasoning" && "Advanced reasoning tasks"}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Model Categories */}
      {modelCategories.map((category) => (
        <section key={category.name} className="mb-10">
          <h2 className="mb-2 text-xl font-semibold text-foreground">{category.name}</h2>
          <p className="mb-4 text-sm text-muted-foreground">{category.description}</p>
          <div className="space-y-3">
            {category.models.map((model) => (
              <div
                key={model.name}
                className="rounded-xl border border-border/50 bg-card/30 p-4"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h3 className="font-semibold text-foreground">{model.name}</h3>
                    <p className="text-xs text-muted-foreground">{model.provider}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <span className="rounded bg-muted/50 px-2 py-1 text-muted-foreground">
                      {model.context} context
                    </span>
                    <span className="flex items-center gap-1 rounded bg-green-500/10 px-2 py-1 text-green-400">
                      <DollarSign className="h-3 w-3" />
                      {model.pricing}
                    </span>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {model.capabilities.map((cap) => {
                    const Icon = capabilityIcons[cap]
                    return (
                      <span
                        key={cap}
                        className={cn("flex items-center gap-1 rounded px-2 py-0.5 text-[10px]", capabilityColors[cap])}
                      >
                        <Icon className="h-2.5 w-2.5" />
                        {cap}
                      </span>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      {/* Choosing a Model */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Choosing a Model</h2>
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <ul className="space-y-3 text-sm text-muted-foreground">
            <li>
              <strong className="text-foreground">For general chat agents:</strong> Claude 3.5 Sonnet or GPT-4o Mini offer the best balance of quality and cost.
            </li>
            <li>
              <strong className="text-foreground">For code assistance:</strong> Claude 3.5 Sonnet or GPT-4 Turbo excel at code generation and debugging.
            </li>
            <li>
              <strong className="text-foreground">For high-volume applications:</strong> Claude 3 Haiku or GPT-4o Mini provide fast, affordable responses.
            </li>
            <li>
              <strong className="text-foreground">For complex reasoning:</strong> Claude 3 Opus or Hermes 3 70B handle multi-step problems well.
            </li>
          </ul>
        </div>
      </section>

      {/* Custom Models */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Using Custom Models</h2>
        <p className="text-sm text-muted-foreground">
          You can also use custom fine-tuned models or self-hosted models by providing an OpenAI-compatible API endpoint 
          in your agent configuration. See the{" "}
          <a href="/docs/config" className="text-primary hover:underline">Configuration docs</a> for details.
        </p>
      </section>
    </article>
  )
}
