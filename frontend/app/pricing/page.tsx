"use client"

import Link from "next/link"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { Footer } from "@/components/footer"
import { Button } from "@/components/ui/button"
import { Check, Zap, Building2, Rocket } from "lucide-react"
import { cn } from "@/lib/utils"

const plans = [
  {
    name: "Hobby",
    description: "Perfect for experimenting with agents",
    price: "Free",
    period: "",
    icon: Zap,
    features: [
      "Up to 3 agents",
      "1,000 messages/month",
      "Community support",
      "Basic analytics",
      "2 channels per agent",
      "OpenRouter integration",
    ],
    cta: "Get Started",
    popular: false,
  },
  {
    name: "Pro",
    description: "For developers building production apps",
    price: "$29",
    period: "/month",
    icon: Rocket,
    features: [
      "Unlimited agents",
      "100,000 messages/month",
      "Priority support",
      "Advanced analytics",
      "All channels",
      "A2A Protocol support",
      "Custom agent cards",
      "Team collaboration (3 seats)",
    ],
    cta: "Start Free Trial",
    popular: true,
  },
  {
    name: "Enterprise",
    description: "For organizations with advanced needs",
    price: "Custom",
    period: "",
    icon: Building2,
    features: [
      "Everything in Pro",
      "Unlimited messages",
      "24/7 dedicated support",
      "Custom integrations",
      "SSO & SAML",
      "SLA guarantee",
      "On-premise deployment",
      "Unlimited team seats",
    ],
    cta: "Contact Sales",
    popular: false,
  },
]

const faqs = [
  {
    question: "What counts as a message?",
    answer: "A message is any interaction between your agent and a user or another agent. This includes both incoming and outgoing messages across all channels."
  },
  {
    question: "Can I change plans later?",
    answer: "Yes! You can upgrade or downgrade your plan at any time. Changes take effect immediately, and we'll prorate the difference."
  },
  {
    question: "Is there a free trial for Pro?",
    answer: "Yes, Pro includes a 14-day free trial with full access to all features. No credit card required to start."
  },
  {
    question: "What happens if I exceed my message limit?",
    answer: "We'll notify you when you're approaching your limit. You can upgrade your plan or purchase additional messages as needed."
  },
]

export default function PricingPage() {
  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <ParticleBackground />
      <Navbar />
      
      <div className="relative z-10 mx-auto max-w-7xl px-4 pb-16 pt-24 sm:px-6 sm:pb-20 sm:pt-32 lg:px-8">
        {/* Header */}
        <div className="mx-auto mb-12 max-w-2xl text-center sm:mb-16">
          <h1 className="text-3xl font-bold text-foreground sm:text-4xl lg:text-5xl">
            Simple, transparent <span className="text-primary">pricing</span>
          </h1>
          <p className="mt-4 text-base text-muted-foreground sm:text-lg">
            Start free and scale as you grow. No hidden fees, no surprises.
          </p>
        </div>

        {/* Pricing Cards */}
        <div className="mx-auto grid max-w-5xl gap-6 sm:gap-8 lg:grid-cols-3">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={cn(
                "relative rounded-2xl border bg-card/50 p-6 backdrop-blur-xl sm:p-8",
                plan.popular 
                  ? "border-primary shadow-[0_0_40px_rgba(249,115,22,0.2)]" 
                  : "border-border/50"
              )}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
                  Most Popular
                </div>
              )}

              <div className="mb-6">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
                  <plan.icon className="h-6 w-6 text-primary" />
                </div>
                <h2 className="text-xl font-bold text-foreground">{plan.name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>
              </div>

              <div className="mb-6">
                <span className="text-4xl font-bold text-foreground">{plan.price}</span>
                <span className="text-muted-foreground">{plan.period}</span>
              </div>

              <ul className="mb-8 space-y-3">
                {plan.features.map((feature, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <span className="text-muted-foreground">{feature}</span>
                  </li>
                ))}
              </ul>

              <Button
                asChild
                className={cn(
                  "w-full",
                  plan.popular
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-muted text-foreground hover:bg-muted/80"
                )}
              >
                <Link href={plan.name === "Enterprise" ? "/contact" : "/signup"}>
                  {plan.cta}
                </Link>
              </Button>
            </div>
          ))}
        </div>

        {/* FAQs */}
        <div className="mx-auto mt-20 max-w-3xl sm:mt-24">
          <h2 className="mb-8 text-center text-2xl font-bold text-foreground sm:mb-12 sm:text-3xl">
            Frequently asked questions
          </h2>
          <div className="grid gap-6 sm:grid-cols-2">
            {faqs.map((faq, i) => (
              <div key={i} className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
                <h3 className="mb-2 font-semibold text-foreground">{faq.question}</h3>
                <p className="text-sm text-muted-foreground">{faq.answer}</p>
              </div>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="mx-auto mt-20 max-w-2xl text-center sm:mt-24">
          <h2 className="text-2xl font-bold text-foreground sm:text-3xl">
            Ready to get started?
          </h2>
          <p className="mt-3 text-muted-foreground">
            Deploy your first agent in under 5 minutes.
          </p>
          <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row sm:gap-4">
            <Button asChild size="lg" className="bg-primary text-primary-foreground">
              <Link href="/signup">Start for Free</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/docs">Read the Docs</Link>
            </Button>
          </div>
        </div>
      </div>
      
      <Footer />
    </main>
  )
}
