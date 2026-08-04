/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        crimson: {
          700: "var(--crimson-700)",
          600: "var(--crimson-600)",
          100: "var(--crimson-100)",
        },
        navy: { 900: "var(--navy-900)", 800: "var(--navy-800)" },
        teal: { 600: "var(--teal-600)" },
        taupe: { 600: "var(--taupe-600)" },
        sand: { 300: "var(--sand-300)", 200: "var(--sand-200)", 50: "var(--sand-50)" },
        moss: { 600: "var(--moss-600)" },
        amber: { 600: "var(--amber-600)" },
        // Semantic text ramp. `colors.text.muted` yields `text-text-muted`,
        // which is the authoring API the design spec names.
        text: {
          body: "var(--text-body)",
          strong: "var(--text-strong)",
          muted: "var(--text-muted)",
          faint: "var(--text-faint)",
          link: "var(--text-link)",
          "link-hover": "var(--text-link-hover)",
          inverse: "var(--text-inverse)",
          "inverse-muted": "var(--text-inverse-muted)",
        },
        status: { live: "var(--status-live)" },
      },
      // Separate from `colors` so the utilities read `border-subtle` rather
      // than `border-border-subtle`, and bare `border` picks up the default.
      borderColor: {
        DEFAULT: "var(--border-default)",
        subtle: "var(--border-subtle)",
        inverse: "var(--border-inverse)",
      },
      fontFamily: {
        display: "var(--font-display)",
        ui: "var(--font-ui)",
        data: "var(--font-data)",
      },
      // Tuples so one utility carries size, leading, and tracking together.
      fontSize: {
        micro: ["12px", { lineHeight: "1.2", letterSpacing: "0.09em" }],
        "body-sm": ["13px", { lineHeight: "1.5" }],
        body: ["15px", { lineHeight: "1.65" }],
        quote: ["20px", { lineHeight: "1.4", letterSpacing: "-0.01em" }],
        "display-sm": ["30px", { lineHeight: "1.15", letterSpacing: "-0.02em" }],
        display: ["38px", { lineHeight: "1.1", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        chip: "var(--radius-chip)",
        control: "var(--radius-control)",
        block: "var(--radius-block)",
        card: "var(--radius-card)",
        panel: "var(--radius-panel)",
        pill: "var(--radius-pill)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        overlay: "var(--shadow-overlay)",
        focus: "var(--shadow-focus)",
      },
      transitionDuration: {
        press: "var(--duration-press)",
        hover: "var(--duration-hover)",
        enter: "var(--duration-enter)",
        panel: "var(--duration-panel)",
      },
      transitionTimingFunction: {
        in: "var(--ease-in)",
        out: "var(--ease-out)",
      },
      // The design ramp is 2/4/6/8/12/16/20/24/32/40/56/72px. Eleven of those
      // twelve are already in Tailwind's default scale; only 72px is missing.
      // Overriding `spacing` wholesale would redefine `p-2` from 8px to 2px
      // across all 16 existing components. Not done.
      spacing: { 18: "72px" },
      // The only looping animation in the system, alongside the mic pulse that
      // reuses it in SP4. Nothing but a recording or live state may loop.
      keyframes: {
        livePulse: { "0%,100%": { opacity: "1" }, "50%": { opacity: ".35" } },
      },
      animation: { livePulse: "livePulse 1.4s ease-in-out infinite" },
    },
  },
  plugins: [],
}
