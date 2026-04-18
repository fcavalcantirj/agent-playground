import * as React from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground border-border h-9 w-full min-w-0 rounded-md border bg-card/60 px-3 py-1 text-base shadow-sm transition-[color,box-shadow,background-color] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
        'hover:border-primary/40 hover:bg-card/80',
        'focus-visible:border-primary focus-visible:bg-card focus-visible:ring-primary/40 focus-visible:ring-[3px]',
        'aria-invalid:ring-destructive/30 aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
