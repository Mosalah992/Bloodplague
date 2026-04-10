import React from "react";

const accentMap = {
  green: "glass-accent-green",
  pink: "glass-accent-pink",
  cyan: "glass-accent-cyan",
  purple: "glass-accent-purple",
  amber: "glass-accent-amber",
  none: ""
};

/**
 * Reusable frosted-glass surface.
 * @param {{ children?: React.ReactNode, className?: string, accent?: keyof typeof accentMap, as?: keyof JSX.IntrinsicElements }} props
 */
export function GlassPanel({ children, className = "", accent = "none", as: Comp = "div", ...rest }) {
  const accentClass = accentMap[accent] || "";
  return (
    <Comp className={`glass rounded-xl ${accentClass} ${className}`.trim()} {...rest}>
      {children}
    </Comp>
  );
}
