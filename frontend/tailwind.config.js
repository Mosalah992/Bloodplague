/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        terminal: {
          base: "#0a0e14",
          panel: "#0d1117",
          panelAlt: "#080c11",
          success: "#4ade80",
          danger: "#f87171",
          warn: "#fbbf24",
          info: "#60a5fa",
          cyan: "#22d3ee",
          purple: "#c084fc",
          gray: "#6b7280",
          grayDark: "#374151"
        },
        glass: {
          bg: "rgba(13, 17, 23, 0.45)",
          border: "rgba(255, 255, 255, 0.08)",
          highlight: "rgba(255, 255, 255, 0.05)"
        },
        agent: {
          shadow: {
            primary: "#4ade80",
            glow: "#22c55e",
            dark: "#052e16",
            accent: "#86efac"
          },
          phantom: {
            primary: "#ec4899",
            glow: "#db2777",
            dark: "#500724",
            accent: "#f9a8d4"
          },
          oracle: {
            primary: "#22d3ee",
            glow: "#0891b2",
            dark: "#083344",
            accent: "#67e8f9"
          },
          cipher: {
            primary: "#c084fc",
            glow: "#9333ea",
            dark: "#3b0764",
            accent: "#e9d5ff"
          },
          sentinel: {
            primary: "#fbbf24",
            glow: "#d97706",
            dark: "#451a03",
            accent: "#fde68a"
          }
        }
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', "monospace"],
        mono: ['"IBM Plex Mono"', "monospace"]
      },
      keyframes: {
        fadeSlide: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" }
        },
        blink: {
          "0%, 49%": { opacity: "1" },
          "50%, 100%": { opacity: "0" }
        },
        pulseGreen: {
          "0%, 100%": { boxShadow: "0 0 3px rgba(74, 222, 128, 0.6)" },
          "50%": { boxShadow: "0 0 10px rgba(74, 222, 128, 0.95)" }
        },
        pulseRed: {
          "0%, 100%": { boxShadow: "0 0 4px rgba(248, 113, 113, 0.28)" },
          "50%": { boxShadow: "0 0 16px rgba(248, 113, 113, 0.52)" }
        },
        floatUp: {
          "0%": { opacity: "0.4", transform: "translateY(8px)" },
          "100%": { opacity: "0", transform: "translateY(-24px)" }
        },
        glitch: {
          "0%, 100%": { transform: "translate(0)" },
          "20%": { transform: "translate(-2px, 1px)" },
          "40%": { transform: "translate(2px, -1px)" },
          "60%": { transform: "translate(-1px, -1px)" },
          "80%": { transform: "translate(1px, 1px)" }
        },
        lockdown: {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "0.65" }
        },
        dataFlow: {
          "0%": { strokeDashoffset: "24" },
          "100%": { strokeDashoffset: "0" }
        },
        pixelFadeIn: {
          "0%": { opacity: "0", transform: "scale(0.92)" },
          "100%": { opacity: "1", transform: "scale(1)" }
        },
        roomPulse: {
          "0%, 100%": { boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.06)" },
          "50%": { boxShadow: "inset 0 0 24px rgba(34, 211, 238, 0.15)" }
        }
      },
      animation: {
        fadeSlide: "fadeSlide 240ms ease-out",
        blink: "blink 1s step-end infinite",
        pulseGreen: "pulseGreen 1.4s ease-in-out infinite",
        pulseRed: "pulseRed 1.8s ease-in-out infinite",
        floatUp: "floatUp 3s ease-out infinite",
        glitch: "glitch 0.4s ease-in-out infinite",
        lockdown: "lockdown 2s ease-in-out infinite",
        dataFlow: "dataFlow 1.2s linear infinite",
        pixelFadeIn: "pixelFadeIn 320ms ease-out",
        roomPulse: "roomPulse 2.4s ease-in-out infinite"
      },
      boxShadow: {
        panel: "0 0 0 1px rgba(34, 211, 238, 0.12), inset 0 1px 0 rgba(34, 211, 238, 0.04)",
        cyan: "0 0 0 1px rgba(34, 211, 238, 0.35)",
        success: "0 0 14px rgba(74, 222, 128, 0.24)",
        danger: "0 0 14px rgba(248, 113, 113, 0.22)",
        glass: "0 8px 32px rgba(0, 0, 0, 0.37), inset 0 1px 0 rgba(255, 255, 255, 0.05)"
      },
      backdropBlur: {
        glass: "16px"
      }
    }
  },
  plugins: []
};
