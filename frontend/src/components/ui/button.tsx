import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export const buttonStyles = cva(
  "inline-flex items-center justify-center rounded-sm border font-medium whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-field-line bg-white text-ink",
        primary: "border-blue bg-blue text-white",
        outline: "border-blue bg-white text-blue2",
        link: "min-h-0 border-0 bg-transparent px-1.5 py-1 text-blue2",
      },
      size: {
        md: "min-h-9 px-3.5",
        lg: "min-h-10 px-4.5",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonStyles>;

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonStyles({ variant, size }), className)} {...props} />;
}
