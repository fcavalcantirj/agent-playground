"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { 
  CreditCard, 
  Download, 
  ExternalLink, 
  Zap, 
  MessageSquare,
  Check,
  ArrowUpRight,
} from "lucide-react"

const invoices = [
  { id: "INV-001", date: "Mar 1, 2024", amount: "$29.00", status: "Paid" },
  { id: "INV-002", date: "Feb 1, 2024", amount: "$29.00", status: "Paid" },
  { id: "INV-003", date: "Jan 1, 2024", amount: "$29.00", status: "Paid" },
  { id: "INV-004", date: "Dec 1, 2023", amount: "$29.00", status: "Paid" },
]

export default function BillingPage() {
  const messagesUsed = 45230
  const messagesLimit = 100000
  const usagePercent = (messagesUsed / messagesLimit) * 100

  return (
    <div>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Billing</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your subscription and billing information
        </p>
      </div>

      <div className="max-w-3xl space-y-6">
        {/* Current Plan */}
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-5 backdrop-blur-sm sm:p-6">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                <span className="font-semibold text-foreground">Pro Plan</span>
                <span className="rounded-full bg-primary/20 px-2 py-0.5 text-xs font-medium text-primary">
                  Active
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                $29/month - Renews on April 1, 2024
              </p>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" size="sm">
                Cancel Plan
              </Button>
              <Button asChild size="sm" className="bg-primary text-primary-foreground">
                <Link href="/pricing">
                  Upgrade
                  <ArrowUpRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </div>
        </div>

        {/* Usage */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Usage This Month</h2>
          </div>

          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Messages processed</span>
            <span className="font-medium text-foreground">
              {messagesUsed.toLocaleString()} / {messagesLimit.toLocaleString()}
            </span>
          </div>
          <Progress value={usagePercent} className="h-2" />
          <p className="mt-2 text-xs text-muted-foreground">
            {(100 - usagePercent).toFixed(1)}% remaining - Resets on April 1, 2024
          </p>
        </div>

        {/* Payment Method */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-primary" />
              <h2 className="font-semibold text-foreground">Payment Method</h2>
            </div>
            <Button variant="ghost" size="sm">
              Update
            </Button>
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-border/50 bg-background/30 p-4">
            <div className="flex h-10 w-14 items-center justify-center rounded bg-gradient-to-br from-blue-600 to-blue-800">
              <span className="text-xs font-bold text-white">VISA</span>
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Visa ending in 4242</p>
              <p className="text-xs text-muted-foreground">Expires 12/2025</p>
            </div>
            <Check className="ml-auto h-5 w-5 text-green-500" />
          </div>
        </div>

        {/* Billing History */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Download className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Billing History</h2>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="py-3 pr-4 text-left font-medium text-muted-foreground">Invoice</th>
                  <th className="py-3 pr-4 text-left font-medium text-muted-foreground">Date</th>
                  <th className="py-3 pr-4 text-left font-medium text-muted-foreground">Amount</th>
                  <th className="py-3 pr-4 text-left font-medium text-muted-foreground">Status</th>
                  <th className="py-3 text-right font-medium text-muted-foreground"></th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id} className="border-b border-border/30">
                    <td className="py-3 pr-4 font-medium text-foreground">{invoice.id}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{invoice.date}</td>
                    <td className="py-3 pr-4 text-foreground">{invoice.amount}</td>
                    <td className="py-3 pr-4">
                      <span className="rounded-full bg-green-500/20 px-2 py-0.5 text-xs font-medium text-green-400">
                        {invoice.status}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs">
                        <Download className="h-3 w-3" />
                        PDF
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Need Help */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <p className="text-sm text-muted-foreground">
            Have questions about billing?{" "}
            <Link href="/contact" className="text-primary hover:underline">
              Contact our support team
              <ExternalLink className="ml-1 inline h-3 w-3" />
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
