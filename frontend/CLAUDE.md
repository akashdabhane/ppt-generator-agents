@AGENTS.md

# Frontend conventions (Next.js 16, React 19, Tailwind v4)

Project-wide rules are in `../CLAUDE.md` and the visual rules are in `../docs/DESIGN.md`. `AGENTS.md` above is managed by `next dev`, so don't edit it.

- Pages live in `src/app/**/page.tsx` and are client components (`"use client"`). Dynamic params are a Promise: `const { id } = use(params)`.
- All HTTP goes through `api` from `@/lib/api` (it adds the Bearer token). Never call `fetch`/`axios` directly with a hand-built URL.
- Server state: TanStack `useQuery`/`useMutation` with keys `["project", id]`, `["documents", id]`, `["presentations", id]`, `["presentation", id]`.
  After a mutation, invalidate or refetch the matching key.
- Client state: Zustand (`@/lib/store`) only for auth. Everything else is local `useState`.
- Styling: Tailwind utility classes only, with light **and** `dark:` variants on every element. Brand button `bg-[#055a44]`. Icons from `lucide-react`.
- Import alias `@/` → `src/`. Components are PascalCase files in `src/components/`.
- Prefer typed API responses (add them to `src/lib/types.ts`) over `any` in new code.
- Check your work with `npm run lint` and `npm run build`.
