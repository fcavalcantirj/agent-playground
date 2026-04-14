"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { Footer } from "@/components/footer"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { 
  BookOpen, 
  Terminal, 
  Code2, 
  Layers, 
  Network,
  Shield,
  Zap,
  Settings,
  MessageSquare,
  ChevronRight,
  Menu,
  X
} from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"

const docsSections = [
  {
    title: "Getting Started",
    items: [
      { title: "Introduction", href: "/docs", icon: BookOpen },
      { title: "Quick Start", href: "/docs/quickstart", icon: Zap },
      { title: "Installation", href: "/docs/installation", icon: Terminal },
    ]
  },
  {
    title: "Core Concepts",
    items: [
      { title: "Agents", href: "/docs/agents", icon: Layers },
      { title: "Models", href: "/docs/models", icon: Code2 },
      { title: "Channels", href: "/docs/channels", icon: MessageSquare },
      { title: "A2A Protocol", href: "/docs/a2a", icon: Network },
    ]
  },
  {
    title: "Reference",
    items: [
      { title: "CLI Reference", href: "/docs/cli", icon: Terminal },
      { title: "API Docs", href: "/docs/api", icon: Code2 },
      { title: "Configuration", href: "/docs/config", icon: Settings },
      { title: "Security", href: "/docs/security", icon: Shield },
    ]
  }
]

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <ParticleBackground />
      <Navbar />
      
      <div className="relative z-10 mx-auto max-w-7xl px-4 pt-20 sm:px-6 sm:pt-24 lg:px-8">
        <div className="flex gap-8">
          {/* Mobile Sidebar Toggle */}
          <Button
            variant="outline"
            size="icon"
            className="fixed bottom-4 right-4 z-50 h-12 w-12 rounded-full shadow-lg lg:hidden"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>

          {/* Sidebar */}
          <aside className={cn(
            "fixed inset-y-0 left-0 z-40 w-72 transform border-r border-border/50 bg-background/95 backdrop-blur-xl transition-transform duration-300 lg:static lg:block lg:w-64 lg:translate-x-0 lg:border-r-0 lg:bg-transparent lg:backdrop-blur-none",
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          )}>
            <ScrollArea className="h-full pb-10 pt-24 lg:pt-0">
              <nav className="space-y-6 px-4 lg:px-0 lg:pr-4">
                {docsSections.map((section) => (
                  <div key={section.title}>
                    <h3 className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {section.title}
                    </h3>
                    <ul className="space-y-1">
                      {section.items.map((item) => {
                        const isActive = pathname === item.href
                        return (
                          <li key={item.href}>
                            <Link
                              href={item.href}
                              onClick={() => setSidebarOpen(false)}
                              className={cn(
                                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                                isActive 
                                  ? "bg-primary/10 text-primary" 
                                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                              )}
                            >
                              <item.icon className="h-4 w-4" />
                              {item.title}
                              {isActive && <ChevronRight className="ml-auto h-4 w-4" />}
                            </Link>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </nav>
            </ScrollArea>
          </aside>

          {/* Overlay for mobile */}
          {sidebarOpen && (
            <div 
              className="fixed inset-0 z-30 bg-background/80 backdrop-blur-sm lg:hidden"
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* Content */}
          <div className="min-w-0 flex-1 pb-16">
            {children}
          </div>
        </div>
      </div>
      
      <Footer />
    </main>
  )
}
