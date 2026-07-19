"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";

/**
 * Light/dark toggle. Hydration-safe (renders a fixed-size placeholder until
 * mounted so server and client markup always match), with a smooth icon
 * crossfade. `className` styles the button shell so each surface (nav over
 * the black hero, themed headers) can blend it in.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={mounted ? `Switch to ${isDark ? "light" : "dark"} mode` : "Toggle theme"}
      title={mounted ? `Switch to ${isDark ? "light" : "dark"} mode` : undefined}
      className={`relative inline-flex h-8 w-8 items-center justify-center rounded-full border transition-colors duration-300 ${className}`}
    >
      {mounted ? (
        <>
          <Sun
            className={`absolute h-4 w-4 transition-all duration-300 ${
              isDark ? "rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100"
            }`}
          />
          <Moon
            className={`absolute h-4 w-4 transition-all duration-300 ${
              isDark ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-0 opacity-0"
            }`}
          />
        </>
      ) : (
        <span className="h-4 w-4" />
      )}
    </button>
  );
}
