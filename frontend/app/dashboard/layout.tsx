"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { cn } from "@/lib/utils"
import { 
  Layers, 
  User,
  Settings,
  CreditCard,
  BarChart3,
  Key,
  Bell,
  Menu,
  X
} from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"

const sidebarItems = [
  { title: "My Agents", href: "/dashboard", icon: Layers },
  { title: "Analytics", href: "/dashboard/analytics", icon: BarChart3 },
  { title: "API Keys", href: "/dashboard/api-keys", icon: Key },
  { title: "Notifications", href: "/dashboard/notifications", icon: Bell },
  { title: "Profile", href: "/dashboard/profile", icon: User },
  { title: "Settings", href: "/dashboard/settings", icon: Settings },
  { title: "Billing", href: "/dashboard/billing", icon: CreditCard },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <ParticleBackground />
      <Navbar
        isLoggedIn={true}
        user={{
          name: "Alex Chen",
          email: "alex@example.com",
        }}
      />
      
      <div className="relative z-10 mx-auto max-w-7xl px-4 pt-20 sm:px-6 sm:pt-24 lg:px-8">
        <div className="flex gap-6 lg:gap-8">
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
            "fixed inset-y-0 left-0 z-40 w-64 transform border-r border-border/50 bg-background/95 backdrop-blur-xl transition-transform duration-300 lg:static lg:block lg:w-56 lg:translate-x-0 lg:border-r-0 lg:bg-transparent lg:backdrop-blur-none",
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          )}>
            <nav className="space-y-1 px-4 pt-24 lg:px-0 lg:pt-0">
              {sidebarItems.map((item) => {
                const isActive = pathname === item.href || 
                  (item.href !== "/dashboard" && pathname.startsWith(item.href))
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setSidebarOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                      isActive 
                        ? "bg-primary/10 text-primary" 
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.title}
                  </Link>
                )
              })}
            </nav>
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
    </main>
  )
}
