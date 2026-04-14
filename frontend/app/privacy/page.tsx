import { Navbar } from "@/components/navbar"
import { Footer } from "@/components/footer"
import { ParticleBackground } from "@/components/particle-background"

export default function PrivacyPage() {
  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <ParticleBackground />
      <Navbar />
      
      <div className="relative z-10 mx-auto max-w-3xl px-4 pb-16 pt-24 sm:px-6 sm:pb-20 sm:pt-32 lg:px-8">
        <h1 className="mb-8 text-3xl font-bold text-foreground sm:text-4xl">Privacy Policy</h1>
        <p className="mb-6 text-sm text-muted-foreground">Last updated: April 14, 2026</p>

        <div className="prose prose-invert max-w-none space-y-6 text-muted-foreground">
          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Introduction</h2>
            <p className="text-sm leading-relaxed">
              Agent Playground, Inc. (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) is committed to protecting your privacy. 
              This Privacy Policy explains how we collect, use, and share information when you use 
              our platform and services.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Information We Collect</h2>
            <h3 className="mb-2 mt-4 text-lg font-medium text-foreground">Account Information</h3>
            <p className="mb-3 text-sm leading-relaxed">
              When you create an account, we collect your name, email address, and authentication 
              credentials (or information from OAuth providers like GitHub or Google).
            </p>
            <h3 className="mb-2 text-lg font-medium text-foreground">Usage Data</h3>
            <p className="mb-3 text-sm leading-relaxed">
              We collect information about how you use our Service, including agent configurations, 
              API calls, message counts, and feature usage.
            </p>
            <h3 className="mb-2 text-lg font-medium text-foreground">Agent Data</h3>
            <p className="text-sm leading-relaxed">
              We process and store data related to your AI agents, including conversation logs, 
              configuration settings, and connected channel information.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">How We Use Your Information</h2>
            <ul className="list-inside list-disc space-y-1 text-sm">
              <li>Provide, maintain, and improve our Service</li>
              <li>Process transactions and send related information</li>
              <li>Send technical notices and support messages</li>
              <li>Respond to your requests and provide customer service</li>
              <li>Monitor and analyze usage patterns and trends</li>
              <li>Detect, prevent, and address fraud and security issues</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Data Sharing</h2>
            <p className="mb-3 text-sm leading-relaxed">We may share your information with:</p>
            <ul className="list-inside list-disc space-y-1 text-sm">
              <li><strong className="text-foreground">Service Providers:</strong> Third parties who help us operate our business</li>
              <li><strong className="text-foreground">AI Model Providers:</strong> OpenRouter and underlying model providers to process requests</li>
              <li><strong className="text-foreground">Channel Integrations:</strong> Platforms like Discord, Telegram, or Slack when you connect them</li>
              <li><strong className="text-foreground">Legal Requirements:</strong> When required by law or to protect our rights</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Data Retention</h2>
            <p className="text-sm leading-relaxed">
              We retain your data for as long as your account is active or as needed to provide 
              services. Conversation logs are retained according to your configured retention policy 
              (default: 30 days). You can request deletion of your data at any time.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Data Security</h2>
            <p className="text-sm leading-relaxed">
              We implement industry-standard security measures to protect your data, including 
              encryption at rest and in transit, access controls, and regular security audits. 
              However, no method of transmission over the Internet is 100% secure.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Your Rights</h2>
            <p className="mb-3 text-sm leading-relaxed">Depending on your location, you may have the right to:</p>
            <ul className="list-inside list-disc space-y-1 text-sm">
              <li>Access the personal data we hold about you</li>
              <li>Request correction of inaccurate data</li>
              <li>Request deletion of your data</li>
              <li>Object to or restrict processing of your data</li>
              <li>Data portability</li>
              <li>Withdraw consent at any time</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Cookies</h2>
            <p className="text-sm leading-relaxed">
              We use cookies and similar technologies to maintain sessions, remember preferences, 
              and analyze usage. You can control cookies through your browser settings.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Children&apos;s Privacy</h2>
            <p className="text-sm leading-relaxed">
              Our Service is not intended for children under 13. We do not knowingly collect 
              information from children under 13. If you believe we have collected such information, 
              please contact us.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">International Transfers</h2>
            <p className="text-sm leading-relaxed">
              Your information may be transferred to and processed in countries other than your 
              own. We ensure appropriate safeguards are in place for such transfers.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Changes to This Policy</h2>
            <p className="text-sm leading-relaxed">
              We may update this Privacy Policy periodically. We will notify you of material 
              changes via email or through the Service. Your continued use after changes indicates 
              acceptance.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">Contact Us</h2>
            <p className="text-sm leading-relaxed">
              If you have questions about this Privacy Policy or your data, please contact us at{" "}
              <a href="mailto:privacy@agentplayground.dev" className="text-primary hover:underline">
                privacy@agentplayground.dev
              </a>
            </p>
          </section>
        </div>
      </div>
      
      <Footer />
    </main>
  )
}
