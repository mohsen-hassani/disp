# DISP Design System

DISP is a personal dashboard/PWA for a single self-hosted user (or small household) — not a
multi-tenant B2B SaaS product and not a marketing site. It's checked in short bursts, often
one-handed on a phone, and used at a desk for denser tasks (tile grids, tables, settings forms).

**Sources**: no codebase, Figma file, or existing brand assets were attached for this project.
Every token, component, and screen here was authored directly from the written product brief
provided at project start (audience, color/type/spacing/motion specs, and the screen inventory
below) — there is no external repo or design file to re-sync against. If a DISP codebase or
Figma file exists, attach it via the Import menu and this design system should be reconciled
against it (see Caveats at the end).

Reference kit: Untitled UI (Figma Community, v2.0) was used only for component *structure*,
spacing discipline, and clean/neutral SaaS polish — not its sales-tool tone or its full
multi-step brand color ramp (see Color below).

## Content fundamentals

- **Tone**: calm, utilitarian, factual. No marketing voice, no encouragement-flavored copy, no
  exclamation points. "No notes yet" not "Looks like it's empty here!".
- **Address**: second person ("your account", "you're offline") for the user's own data; no
  first-person plural ("we"/"our") — this isn't a company talking to a customer.
- **Casing**: sentence case everywhere (buttons, headings, nav labels) — never Title Case or
  ALL CAPS. "Create API token", not "Create API Token".
- **Errors**: state what happened and what to do, without blame or apology padding. "Couldn't
  load this tile." + a retry action, not "Oops! Something went wrong on our end."
- **Auth copy is deliberately terse and closed**: "Contact your admin if you don't have an
  account or need a password reset." No self-serve recovery flow exists, so copy never implies
  one.
- **Serious moments get serious copy**: the one-time token secret dismissal reads "This is
  shown once. Copy it now — it can't be retrieved again." — explicit, not cute.
- **No emoji.** Not in copy, not as icons, not in empty states.
- Acronyms (API, PWA) stay uppercase; product/module names ("Notes", "Account", "Dashboard")
  are capitalized as proper nouns when referring to the section, lowercase in prose ("your notes").

## Visual foundations

- **Color**: neutral surfaces plus exactly one accent (light `#2f5fd0` / dark `#7ba0f0`, both
  AA-checked against their surface tokens). No secondary or tertiary brand hues, no gradients.
  An internal gray/accent ramp exists only inside `tokens/colors.css` to build the semantic
  aliases — components never see raw grays (see "Open decision" below).
- **Type**: system font stack only (no webfonts) — this avoids a render-blocking request and a
  licensing question, not a style call. Small, restrained scale (0.75–2rem), semibold headings,
  regular/medium body. Prose (note bodies, help text) caps at 68ch.
- **Spacing/density**: 4px base scale (4/8/12/16/24/32/48). High density on desktop (32px rows,
  tight gutters); generous 44px+ touch targets on mobile. Mobile-first breakpoints: base single
  column + bottom nav, md (768px) introduces the side nav and two-column tile grid, xl (1280px)
  caps content at 1200px centered.
- **Elevation**: borders + a subtle surface-step background (`surface` → `surface-raised` →
  `surface-sunken`) do the work everywhere. Exactly one shadow token (`--shadow-overlay`) is
  reserved for the three overlay surfaces — dialogs, dropdowns, toasts. Cards never get a shadow.
  No left-border-accent card pattern.
  imagery: **none** — DISP has no marketing imagery, hero shots, or decorative illustration.
  Empty states use a single muted icon glyph, never illustration.
- **Backgrounds**: flat surface color only. No gradients, no textures, no patterns, no blur.
- **Motion**: minimal and fast — 120ms for state changes (hover/press/toggle), 200ms for
  overlays, always `cubic-bezier(0.2, 0, 0, 1)`. No shimmer skeletons (a static muted block
  instead), no parallax, no scroll-linked animation. Everything collapses to 0ms under
  `prefers-reduced-motion`.
- **Hover/press states**: hover darkens/lightens via `color-mix()` against the existing token
  (never a new hardcoded color); press states scale buttons to 0.97 or darken slightly. No
  opacity-based hover on solid-fill buttons (contrast risk); ghost/icon buttons do use a subtle
  surface-step background on hover.
- **Radius**: sm 6px (controls/inputs), md 10px (cards), lg 16px (dialogs). No pill-shaped
  buttons; pills (`--radius-full`) are reserved for badges/tags/avatars/switches.
  Cards: 1px border (`--color-border`), `--radius-md`, `--color-surface-raised` fill, no shadow.
- **Theming**: light, dark, and system (`prefers-color-scheme`). Every screen and component is
  designed for both — dark isn't a tinted afterthought.
- **Transparency/blur**: none. Dialog scrims are a flat `rgba(13,15,18,0.4)` overlay, no
  backdrop-filter blur.

## Iconography

**CDN substitution, flagged**: no icon codebase, sprite, or Figma icon library was provided.
Icons use [Lucide](https://lucide.dev) (MIT-licensed, stroke-based, 2px weight) loaded per-icon
from the `unpkg.com/lucide-static` CDN via the `Icon` component, which masks the SVG with
`currentColor` so it inherits text color and adapts to theme automatically. This is a
substitution, not a confirmed brand choice — if DISP's real codebase uses a different icon set,
swap `Icon.jsx`'s CDN source and re-verify the `icons.card.html` specimen.
No icon font, no emoji-as-icon, no unicode-character icons. No PNG icons.

## Open decision — flagged, not silently resolved

The brief asked whether to expose a broader internal gray/brand ramp (Untitled-UI style) even
if only the semantic layer stays component-facing. **Resolved as: yes, kept internal.**
`tokens/colors.css` defines a private `--gray-0…--gray-950` + `--accent-500/600` ramp used only
to build the eleven authoritative semantic tokens; no component or card ever references a raw
gray step. If a different ramp already exists in the real codebase, replace this one directly —
nothing downstream depends on the private step names.

## Index

- `styles.css` — root stylesheet, imports everything below.
- `tokens/` — `colors.css` (surface/text/border/semantic + private ramp), `typography.css`,
  `spacing.css`, `radius.css`, `motion.css` (incl. reduced-motion reset), `base.css` (resets, link states).
- `guidelines/` — 12 foundation specimen cards (Colors, Type, Spacing groups in the Design System tab).
- `components/core/` — Button, IconButton, Icon, Badge, Tag, Avatar
- `components/forms/` — TextField, SelectField, SecretField, Switch (the JSON-Schema field set)
- `components/feedback/` — Toast, EmptyState, ErrorView, OfflineBanner, SkeletonBlock
- `components/overlay/` — Dialog, Tooltip, Menu
- `components/navigation/` — TopBar, SideNav, BottomNav, Tabs
- `components/data/` — TileCard, TileItem
- `ui_kits/disp-client/` — click-through recreation: login, invite (pending/expired), dashboard
  tile grid, Notes (list/detail/share), Account (details/tokens/invites).
- `thumbnail.html` — homepage tile.
- `SKILL.md` — portable skill file for Claude Code.

## Caveats — please help iterate

- **No source material was attached.** Every value here (colors, spacing, copy tone) comes from
  the written brief, not a real codebase or Figma file — if DISP has an actual repo or design
  file, attach it and I'll reconcile this system against ground truth rather than the brief.
- **Icons are a Lucide CDN substitution**, not confirmed against a real icon set — flag if wrong.
- **No logo exists** — the wordmark "DISP" in system-font type stands in for a mark everywhere
  one would go (top bar, thumbnail, auth screen). Provide a logo if one exists.
- The UI kit demonstrates the desktop (side-nav) layout in depth; the mobile bottom-nav layout
  is built as a component (`BottomNav`) but the kit doesn't yet show a full mobile-width click-through — tell me if you want a dedicated mobile pass.
- No PWA install-prompt or "update available" toast composition beyond the base `Toast`
  component — flag if you want a dedicated install-prompt design.
