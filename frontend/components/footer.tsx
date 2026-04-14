import Link from "next/link"
import { Terminal, Github, Twitter, ExternalLink } from "lucide-react"

const footerLinks = {
  Product: [
    { name: "Playground", href: "/playground" },
    { name: "Pricing", href: "/pricing" },
    { name: "Dashboard", href: "/dashboard" },
    { name: "API Keys", href: "/dashboard/api-keys" },
  ],
  Resources: [
    { name: "Documentation", href: "/docs" },
    { name: "Quick Start", href: "/docs/quickstart" },
    { name: "API Reference", href: "/docs/api" },
    { name: "CLI Reference", href: "/docs/cli" },
  ],
  Ecosystem: [
    { name: "ClawClones", href: "https://clawclones.com/#clones", external: true },
    { name: "Hermes Agent", href: "https://hermes-agent.nousresearch.com/", external: true },
    { name: "OpenRouter", href: "https://openrouter.ai/models", external: true },
    { name: "Nous Research", href: "https://nousresearch.com", external: true },
  ],
  Company: [
    { name: "Contact", href: "/contact" },
    { name: "Privacy Policy", href: "/privacy" },
    { name: "Terms of Service", href: "/terms" },
    { name: "GitHub", href: "https://github.com", external: true },
  ],
}

const socialLinks = [
  { name: "GitHub", icon: Github, href: "https://github.com" },
  { name: "Twitter", icon: Twitter, href: "#" },
]

export function Footer() {
  return (
    <footer className="relative border-t border-border bg-card/30 backdrop-blur-sm">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-12 lg:px-8 lg:py-16">
        <div className="grid grid-cols-2 gap-6 sm:gap-8 md:grid-cols-3 lg:grid-cols-6 lg:gap-12">
          {/* Brand */}
          <div className="col-span-2 md:col-span-3 lg:col-span-2">
            <Link href="/" className="mb-3 flex items-center gap-2 sm:mb-4">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary sm:h-8 sm:w-8">
                <Terminal className="h-4 w-4 text-primary-foreground sm:h-5 sm:w-5" />
              </div>
              <span className="text-base font-bold text-foreground sm:text-lg">
                Agent<span className="text-primary">Playground</span>
              </span>
            </Link>
            <p className="mb-4 max-w-xs text-sm text-muted-foreground sm:mb-6">
              Deploy any ClawClone with any OpenRouter model. N agents, any combination, across all channels.
            </p>
            <div className="flex items-center gap-2 sm:gap-3">
              {socialLinks.map((social) => (
                <a
                  key={social.name}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary sm:h-9 sm:w-9"
                >
                  <social.icon className="h-4 w-4" />
                  <span className="sr-only">{social.name}</span>
                </a>
              ))}
            </div>
          </div>

          {/* Links */}
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h3 className="mb-3 text-sm font-semibold text-foreground sm:mb-4">{category}</h3>
              <ul className="space-y-2 sm:space-y-3">
                {links.map((link) => (
                  <li key={link.name}>
                    {link.external ? (
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-primary sm:text-sm"
                      >
                        {link.name}
                        <ExternalLink className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        className="text-xs text-muted-foreground transition-colors hover:text-primary sm:text-sm"
                      >
                        {link.name}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom */}
        <div className="mt-8 flex flex-col items-center justify-between gap-3 border-t border-border pt-6 sm:mt-12 sm:flex-row sm:gap-4 sm:pt-8 lg:mt-16">
          <p className="text-center text-xs text-muted-foreground sm:text-left sm:text-sm">
            &copy; {new Date().getFullYear()} Agent Playground. Open Source under MIT License.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-muted-foreground sm:gap-4 sm:text-sm">
            <a href="https://clawclones.com" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 transition-colors hover:text-primary">
              ClawClones.com
              <ExternalLink className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            </a>
            <a href="https://nousresearch.com" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 transition-colors hover:text-primary">
              Nous Research
              <ExternalLink className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
