# Design System

There are two separate visual systems: the **web app UI** (Tailwind) and the **generated decks** (python-pptx themes).
Don't mix them up.

## Part A — Web app UI (`frontend/`)

**Personality:** calm, professional, "document workspace". Emerald brand on warm stone neutrals, with a subtle grid background.

### Colour tokens

| Role | Light | Dark |
|---|---|---|
| Page background (`--background`) | `#f4f6f5` | `#080b09` |
| Foreground text (`--foreground`) | `#0f172a` | `#f8fafc` |
| Grid line (`--grid-line`) | `rgba(0,0,0,.04)` | `rgba(255,255,255,.05)` |
| Card / surface | `bg-white/80` | `dark:bg-[#0d120f]` |
| Border | `border-stone-200` | `dark:border-zinc-800` |
| Primary button / active pill | `bg-[#055a44]`, hover `#044836`, `text-white` | same |
| Brand text / icons / links | `text-emerald-700` | `dark:text-emerald-400` |
| Headings | `text-slate-900` | `dark:text-white` |
| Muted text | `text-slate-500` | `dark:text-zinc-400` |
| Inputs | `bg-stone-50 border-stone-300` | `dark:bg-zinc-950 dark:border-zinc-800` |
| Focus ring | `focus:ring-2 focus:ring-emerald-500` | same |

CSS variables live in `frontend/src/app/globals.css`. Dark mode is **class-based** (`.dark` on `<html>`,
Tailwind v4 `@custom-variant dark`), saved to `localStorage["app_theme"]` and applied before first paint by an inline
script in `app/layout.tsx`. `Providers.tsx` reads it with `useSyncExternalStore`. Light is the default.
**Every new element needs both light and dark classes.**

### Status colours (badges)

- Success / `INDEXED` / `COMPLETED`: `bg-emerald-100/80 text-emerald-800 border-emerald-300/80` (dark: `emerald-950/60`, `emerald-300`, `emerald-800`)
- Error / `FAILED`: `bg-red-100 text-red-700 border-red-300` (dark: `red-950/60`, `red-300`, `red-800`)
- In progress: `bg-amber-100 text-amber-700 border-amber-300` + a spinning `Clock` icon
- Badge shape: `text-xs px-3 py-1 rounded-full font-semibold`

### Typography

- Font: **Inter** (`next/font/google`) across the app. Use `font-mono` for metadata (file size, type, email chip).
- Page title: `text-2xl sm:text-3xl font-extrabold tracking-tight`
- Section title: `text-lg`/`text-xl font-bold`
- Form label: `text-xs font-semibold uppercase tracking-wider`
- Body / help: `text-sm` / `text-xs`

### Shape, spacing, elevation

- Radius: cards and panels `rounded-2xl`; list items `rounded-xl`; inputs `rounded-lg`/`rounded-xl`; pills, badges and tab bars `rounded-full`.
- Card padding `p-6 sm:p-8`; list rows `p-4`; page wrapper `max-w-7xl mx-auto p-4 sm:p-6 lg:p-8`; vertical rhythm `space-y-6`/`space-y-8`.
- Shadows are light: `shadow-xs`. Use `shadow-xl` only on the main focused panel (the Generate studio).
- Interactions: `transition` on everything, hover border `hover:border-emerald-500/50`, destructive hover `hover:text-red-500`.

### Components & patterns

- Icons: **lucide-react** only, usually `w-4 h-4` (inline) or `w-5 h-5` (in icon tiles).
- Icon tile: `p-3 rounded-xl bg-emerald-100/70 text-emerald-700 border border-emerald-200` (+ dark variants).
- Tabs: pill bar (`rounded-full p-1.5 bg-stone-200/70`) where the active tab is `bg-[#055a44] text-white`.
- Navbar: sticky, translucent `bg-white/80 backdrop-blur-md`, `h-16`.
- Empty states: centered muted text inside a bordered `rounded-xl` panel.
- Responsive: mobile-first, with `sm:`/`md:` breakpoints. Grids collapse to one column.

## Part B — Generated deck themes (`backend/app/presentation/themes.py`)

The slide size is 16:9, 10 × 5.625 in. Geometry comes **only** from `LayoutEngine` (see ARCHITECTURE §5).

| Theme | Primary | Secondary | Accent | Background | Text | Card | Fonts (heading / body) |
|---|---|---|---|---|---|---|---|
| Professional (default) | 15,44,89 navy | 53,89,143 | 217,119,6 amber | white | 30,41,59 | 241,245,249 | Arial / Calibri |
| Minimal | 17,24,39 | 75,85,99 | 99,102,241 indigo | 250,250,250 | 17,24,39 | 243,244,246 | Helvetica / Arial |
| Dark | 244,244,245 | 161,161,170 | 59,130,246 blue | 18,24,38 | 226,232,240 | 30,41,59 | Trebuchet MS / Calibri |
| Corporate | 0,64,128 | 0,102,204 | 0,153,76 emerald | white | 33,37,41 | 238,242,246 | Georgia / Calibri |
| Modern | 13,148,136 teal | 45,212,191 | 244,63,94 rose | white | 15,23,42 | 240,253,250 | Segoe UI / Segoe UI |

Type sizes (pt): title 36 (Minimal 34), subtitle 20 (18), heading 24 (22), body 14.
Fixed in the renderer: footer citations 9 pt italic, table header 12 pt bold white on primary, table body 11 pt
with alternating `card_bg`/`background` rows, two-column heads 16 / items 13, quote 20 italic, summary 14 bold in accent with a "✔" prefix.

### Rules for deck design changes
- Add a theme by adding an entry to `THEMES` and to the theme `<select>` in `projects/[id]/page.tsx`.
- Never hard-code colours in the renderer. Always read `self.theme.colors.*`.
- Any new element must get its `Rect` from `LayoutEngine` and pass `validate_bounds`.
- Some two-column/quote text currently falls back to the default black. Use `theme.colors.text` in new code, since black text is invisible on the Dark theme.
