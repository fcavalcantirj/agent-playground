"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { apiPost } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Terminal,
  Menu,
  X,
  ChevronDown,
  User,
  Settings,
  LogOut,
  CreditCard,
  Bell,
  BookOpen,
  MessageCircle,
  Github,
  ExternalLink,
  Layers,
} from "lucide-react"

interface NavbarProps {
  isLoggedIn?: boolean
  user?: {
    name: string
    email: string
    avatar?: string
  }
}

export function Navbar({ isLoggedIn = false, user }: NavbarProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const router = useRouter()

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between sm:h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 group shrink-0">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary transition-all group-hover:animate-pulse-glow sm:h-8 sm:w-8">
              <Terminal className="h-4 w-4 text-primary-foreground sm:h-5 sm:w-5" />
            </div>
            <span className="text-base font-bold text-foreground sm:text-lg">
              Agent<span className="text-primary">Playground</span>
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden items-center gap-1 md:flex">
            <NavLink href="/playground">Playground</NavLink>
            <NavLink href="/pricing">Pricing</NavLink>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground">
                  Ecosystem
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild>
                  <a href="https://clawclones.com/#clones" target="_blank" rel="noopener noreferrer" className="flex items-center justify-between">
                    <span className="flex items-center">
                      <Layers className="mr-2 h-4 w-4" />
                      ClawClones
                    </span>
                    <ExternalLink className="h-3 w-3 text-muted-foreground" />
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <a href="https://hermes-agent.nousresearch.com/" target="_blank" rel="noopener noreferrer" className="flex items-center justify-between">
                    <span className="flex items-center">
                      <Terminal className="mr-2 h-4 w-4" />
                      Hermes Agent
                    </span>
                    <ExternalLink className="h-3 w-3 text-muted-foreground" />
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <a href="https://openrouter.ai/models" target="_blank" rel="noopener noreferrer" className="flex items-center justify-between">
                    <span className="flex items-center">
                      <MessageCircle className="mr-2 h-4 w-4" />
                      OpenRouter Models
                    </span>
                    <ExternalLink className="h-3 w-3 text-muted-foreground" />
                  </a>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="flex items-center justify-between">
                    <span className="flex items-center">
                      <Github className="mr-2 h-4 w-4" />
                      GitHub
                    </span>
                    <ExternalLink className="h-3 w-3 text-muted-foreground" />
                  </a>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground">
                  Docs
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem asChild>
                  <Link href="/docs">
                    <BookOpen className="mr-2 h-4 w-4" />
                    Getting Started
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/docs/cli">
                    <Terminal className="mr-2 h-4 w-4" />
                    CLI Reference
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/docs/api">
                    <MessageCircle className="mr-2 h-4 w-4" />
                    API Docs
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Right Section */}
          <div className="hidden items-center gap-2 md:flex lg:gap-3">
            {isLoggedIn ? (
              <>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="relative transition-colors hover:bg-primary/10 hover:text-primary">
                      <Bell className="h-5 w-5" />
                      <span className="absolute right-1 top-1 flex h-2.5 w-2.5 items-center justify-center">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
                      </span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-80 border-border/50 bg-card/95 backdrop-blur-xl">
                    <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
                      <p className="text-sm font-semibold">Notifications</p>
                      <Link href="/dashboard/notifications" className="text-xs text-primary transition-colors hover:text-primary/80 hover:underline">
                        View all
                      </Link>
                    </div>
                    <div className="max-h-72 overflow-y-auto">
                      <DropdownMenuItem className="flex cursor-pointer flex-col items-start gap-1 px-3 py-2.5 transition-colors hover:bg-primary/5">
                        <div className="flex items-center gap-2">
                          <span className="h-2 w-2 rounded-full bg-green-500" />
                          <span className="text-sm font-medium">Agent deployed</span>
                        </div>
                        <span className="pl-4 text-xs text-muted-foreground">Customer Support Bot is now live</span>
                        <span className="pl-4 text-[10px] text-muted-foreground">5 min ago</span>
                      </DropdownMenuItem>
                      <DropdownMenuItem className="flex cursor-pointer flex-col items-start gap-1 px-3 py-2.5 transition-colors hover:bg-primary/5">
                        <div className="flex items-center gap-2">
                          <span className="h-2 w-2 rounded-full bg-amber-500" />
                          <span className="text-sm font-medium">Usage alert</span>
                        </div>
                        <span className="pl-4 text-xs text-muted-foreground">80% of monthly quota used</span>
                        <span className="pl-4 text-[10px] text-muted-foreground">2 hours ago</span>
                      </DropdownMenuItem>
                    </div>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem asChild className="justify-center transition-colors hover:bg-primary/5">
                      <Link href="/dashboard/notifications" className="text-primary">
                        See all notifications
                      </Link>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="gap-2 pl-2 pr-3 transition-colors hover:bg-primary/10">
                      <Avatar className="h-7 w-7 ring-2 ring-transparent transition-all group-hover:ring-primary/30">
                        <AvatarImage src={user?.avatar} />
                        <AvatarFallback className="bg-primary text-xs text-primary-foreground">
                          {user?.name?.charAt(0) || "U"}
                        </AvatarFallback>
                      </Avatar>
                      <span className="hidden text-sm lg:inline">{user?.name || "User"}</span>
                      <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform duration-200" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56 border-border/50 bg-card/95 backdrop-blur-xl">
                    <div className="px-2 py-1.5">
                      <p className="text-sm font-medium">{user?.name}</p>
                      <p className="text-xs text-muted-foreground">{user?.email}</p>
                    </div>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem asChild>
                      <Link href="/dashboard/profile">
                        <User className="mr-2 h-4 w-4" />
                        Profile
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link href="/dashboard">
                        <Layers className="mr-2 h-4 w-4" />
                        My Agents
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link href="/dashboard/settings">
                        <Settings className="mr-2 h-4 w-4" />
                        Settings
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link href="/dashboard/billing">
                        <CreditCard className="mr-2 h-4 w-4" />
                        Billing
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onSelect={async (e) => {
                        e.preventDefault()
                        try {
                          await apiPost("/api/v1/auth/logout", {})
                        } catch {
                          // Server-side session may already be gone; fall
                          // through to redirect so the UI lands at /login
                          // regardless of backend state.
                        }
                        router.push("/login")
                      }}
                    >
                      <LogOut className="mr-2 h-4 w-4" />
                      Log out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link href="/login">Log in</Link>
                </Button>
                <Button asChild size="sm" className="bg-primary text-primary-foreground hover:bg-primary/90">
                  <Link href="/signup">Get Started</Link>
                </Button>
              </>
            )}
          </div>

          {/* Mobile Menu Button */}
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 md:hidden"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          >
            {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>
      </div>

      {/* Mobile Menu */}
      <div
        className={cn(
          "glass overflow-hidden transition-all duration-300 md:hidden",
          isMobileMenuOpen ? "max-h-[28rem]" : "max-h-0"
        )}
      >
        <div className="space-y-1 px-4 py-4">
          <MobileNavLink href="/playground" onClick={() => setIsMobileMenuOpen(false)}>Playground</MobileNavLink>
          <MobileNavLink href="/pricing" onClick={() => setIsMobileMenuOpen(false)}>Pricing</MobileNavLink>
          <MobileNavLink href="/docs" onClick={() => setIsMobileMenuOpen(false)}>Documentation</MobileNavLink>
          
          <div className="py-2">
            <p className="px-3 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Ecosystem</p>
            <MobileNavLink href="https://clawclones.com/#clones" onClick={() => setIsMobileMenuOpen(false)}>ClawClones</MobileNavLink>
            <MobileNavLink href="https://hermes-agent.nousresearch.com/" onClick={() => setIsMobileMenuOpen(false)}>Hermes Agent</MobileNavLink>
            <MobileNavLink href="https://openrouter.ai/models" onClick={() => setIsMobileMenuOpen(false)}>OpenRouter</MobileNavLink>
          </div>

          <div className="flex gap-3 pt-4">
            {isLoggedIn ? (
              <Button asChild variant="outline" className="flex-1">
                <Link href="/dashboard">My Agents</Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="outline" className="flex-1">
                  <Link href="/login">Log in</Link>
                </Button>
                <Button asChild className="flex-1 bg-primary text-primary-foreground">
                  <Link href="/signup">Get Started</Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
    >
      {children}
    </Link>
  )
}

function MobileNavLink({ href, children, onClick }: { href: string; children: React.ReactNode; onClick?: () => void }) {
  const isExternal = href.startsWith("http")
  
  if (isExternal) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={onClick}
        className="flex items-center justify-between rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
      >
        {children}
        <ExternalLink className="h-3 w-3" />
      </a>
    )
  }
  
  return (
    <Link
      href={href}
      onClick={onClick}
      className="block rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
    >
      {children}
    </Link>
  )
}
