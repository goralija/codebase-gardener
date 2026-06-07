import { cn } from "@/lib/utils"

export const GARDENER_LOGO_SRC = "/brand/gardener-logo.png"
export const GARDENER_MASCOT_SRC = "/brand/gardener-mascot.png"

type BrandImageProps = {
  className?: string
}

export function GardenerLogo({ className }: BrandImageProps) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className={cn(
        "rounded-md bg-white object-cover ring-1 ring-border",
        className
      )}
      src={GARDENER_LOGO_SRC}
    />
  )
}

export function GardenerMascot({ className }: BrandImageProps) {
  return (
    <img
      alt="Codebase Gardener mascot"
      className={cn(
        "rounded-md bg-white object-cover ring-1 ring-border",
        className
      )}
      src={GARDENER_MASCOT_SRC}
    />
  )
}
