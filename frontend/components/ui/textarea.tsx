import * as React from 'react'

import { cn } from '@/lib/utils'

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'border-border placeholder:text-muted-foreground flex field-sizing-content min-h-16 w-full rounded-md border bg-card/60 px-3 py-2 text-base shadow-sm transition-[color,box-shadow,background-color] outline-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
        'hover:border-primary/40 hover:bg-card/80',
        'focus-visible:border-primary focus-visible:bg-card focus-visible:ring-primary/40 focus-visible:ring-[3px]',
        'aria-invalid:ring-destructive/30 aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  )
}

export { Textarea }
