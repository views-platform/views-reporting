#!/usr/bin/env bash
# Regenerate the vendored Tailwind CSS asset (views_reporting/reports/assets/tailwind.css).
#
# Why this exists (register C-28): exported reports must render fully offline, so the
# Tailwind utilities they use are vendored as a static CSS shipped in the wheel instead
# of JIT-compiled from the Play CDN at view time. Tailwind v3 is JIT-only (no downloadable
# full build), so the asset is produced by running the Tailwind CLI ONCE over the
# templates + the repo's theme tokens and committing the result. **Node is needed only to
# regenerate** — never at runtime or in the wheel.
#
# Run this whenever the templates add/remove Tailwind classes or the theme changes, then
# commit the updated asset. The content scanner reads every class token in the .py files
# (including inside f-strings), so it covers the classes actually used (C-187); the
# coverage is also guarded by tests/test_offline_assets.py.
#
# Usage:  bash scripts/build_tailwind_css.sh   (requires node/npx + network on first run)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/views_reporting/reports/assets/tailwind.css"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Theme tokens — kept in sync with views_reporting/reports/styles/tailwind.py.
cat > "$WORK/tailwind.config.js" <<EOF
module.exports = {
  content: ["$REPO/views_reporting/**/*.py"],
  theme: { extend: {
    colors: {
      primary: '#6750A4', 'on-primary': '#FFFFFF', 'primary-container': '#EADDFF',
      secondary: '#625B71', 'on-secondary': '#FFFFFF', 'secondary-container': '#E8DEF8',
      tertiary: '#7D5260', 'on-tertiary': '#FFFFFF', 'tertiary-container': '#FFD8E4',
      error: '#B3261E', 'on-error': '#FFFFFF', 'error-container': '#F9DEDC',
      outline: '#79747E', background: '#FFFFFF', 'on-background': '#1F1F1F',
      surface: '#FFFFFF', 'on-surface': '#1F1F1F',
      'surface-variant': '#F3EDF7', 'on-surface-variant': '#49454F',
    },
    fontFamily: { sans: ['Roboto', 'system-ui', 'sans-serif'] },
    borderRadius: { 'sm': '8px', 'md': '12px', 'lg': '16px', 'xl': '28px' },
    boxShadow: {
      card: '0 4px 6px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.1)',
      'card-hover': '0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)',
    },
  }},
}
EOF
printf '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n' > "$WORK/input.css"

npx -y tailwindcss@3 -c "$WORK/tailwind.config.js" -i "$WORK/input.css" -o "$OUT" --minify
echo "Wrote $OUT ($(wc -c < "$OUT") bytes)"
