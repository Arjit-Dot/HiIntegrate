import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent px-[9px] py-0.5 text-xs font-semibold whitespace-nowrap transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        destructive: "bg-destructive text-white",
        outline: "border-border text-foreground",
        ghost: "",
        link: "text-primary underline-offset-4",
        healthy: "bg-[#dcfce7] text-[#15803d]",
        success: "bg-[#dcfce7] text-[#15803d]",
        set: "bg-[#dcfce7] text-[#15803d]",
        degraded: "bg-[#fef3c7] text-[#b45309]",
        running: "bg-[#fef3c7] text-[#b45309]",
        notset: "bg-[#fef3c7] text-[#b45309]",
        failing: "bg-[#fee2e2] text-[#b91c1c]",
        failed: "bg-[#fee2e2] text-[#b91c1c]",
        disabled: "bg-[#e8ecf2] text-[#64748b]",
        never_run: "bg-[#e8ecf2] text-[#64748b]",
        schema: "bg-[#eef0ff] text-[#3730a3]",
        trigger: "bg-[#e0f2fe] text-[#0369a1]",
        pull: "bg-[#e0e7ff] text-[#3730a3]",
        lookup: "bg-[#f3e8ff] text-[#6b21a8]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
