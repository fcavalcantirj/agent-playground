import { Skeleton } from "@/components/ui/skeleton"

export default function DocsLoading() {
  return (
    <article className="max-w-3xl">
      {/* Header */}
      <div className="mb-8">
        <Skeleton className="h-10 w-64 sm:h-12 sm:w-80" />
        <Skeleton className="mt-3 h-5 w-full max-w-xl" />
      </div>

      {/* Content blocks */}
      <div className="space-y-8">
        {/* Section 1 */}
        <section>
          <Skeleton className="mb-4 h-7 w-48" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        </section>

        {/* Cards Grid */}
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="rounded-xl border border-border/50 bg-card/30 p-5"
            >
              <Skeleton className="mb-3 h-10 w-10 rounded-lg" />
              <Skeleton className="mb-2 h-5 w-32" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="mt-1 h-3 w-2/3" />
            </div>
          ))}
        </div>

        {/* Section 2 */}
        <section>
          <Skeleton className="mb-4 h-7 w-56" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        </section>

        {/* Code Block */}
        <div className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <Skeleton className="mb-3 h-4 w-24" />
          <div className="space-y-2">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
      </div>
    </article>
  )
}
