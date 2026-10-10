# AI DESIGN TOOLBOX — 25 curated references

This is a **reference catalog** for Codex, ChatGPT, and Chat On Steroids. It does not install third-party dependencies, grant PC access, or override project instructions. The URLs were user-supplied; verify availability, licensing, and safety before use.

## Design inspiration and UX research
1. [jiro.build](https://jiro.build) — AI-ready design prompts, to critique and adapt.
2. [Minimal Gallery](https://minimal.gallery) — selected minimalist websites; extract hierarchy and spacing.
3. [Kage](https://kage.design) — visual UI inspiration and prompt references.
4. [Refero Styles](https://styles.refero.design) — typography, layout, and interface patterns.
5. [Component Gallery](https://component.gallery) — compare accessible component conventions.
6. [AppShot Gallery](https://appshot.gallery) — actual mobile screen references.
7. [DESIGNmd](https://designmd.ai) — markdown design systems / token ideas.
8. [VibePrompt](https://vibeprompts.dev) — initial prompt ideas for product screens.

## Web components and building blocks
9. [21st.dev](https://21st.dev) — inspect agent-oriented component examples; review code/license before use.
11. [shadcn/ui](https://ui.shadcn.com) — composable, accessible React web UI patterns.
12. [Aceternity UI](https://ui.aceternity.com) — animated React/Tailwind components.
13. [Magic UI](https://magicui.design) — presentation and web micro-interactions.
15. [Uiverse](https://uiverse.io) — community components; audit security and accessibility.
16. [UIAble](https://uiable.com) — interface component inspiration.

## Interaction and motion
10. [Kinetics](https://kinetics.colorion.co) — motion references and React examples.
14. [Motion Primitives](https://motion-primitives.com) — interaction primitives.
18. [MicroKit UI](https://microkit.co) — micro-interaction references.
19. [Liquid Glass](https://glass.samasante.com) — glass/refraction treatment, only if useful.
20. [CSS Text Effects](https://text-effects.colorion.co) — typography animations.
21. [Circle Loaders](https://circleloaders.dominikakissi.com) — progress/loading animations.
22. [Gradient Buttons](https://gradientbuttons.colorion.co) — CTA treatment references.
25. [Anime.js](https://animejs.com) — web animation library (not React Native itself).

## Media and specialist UI
17. [mapcn](https://mapcn.dev) — maps and route components when product actually needs them.
23. [Kitbitz](https://kitbitz.art) — illustration reference; check reuse rights.
24. [3Dicons](https://3dicons.co) — 3D interface asset reference; check license and performance.

## Agent rules
1. Read this catalog only for design/UI/product work; it is irrelevant to backend-only smoke tests or security fixes.
2. Inspect the actual product, existing components, design system, stack and user-approved UX before suggesting a redesign.
3. Select at most 1–3 relevant references and explain which **principles**, not proprietary assets, are being adapted.
4. Do not install packages, tools, browser extensions, or MCP servers just because they appear here. Verify licenses, version, supply chain, accessibility, performance, and compatibility first.
5. React DOM/CSS/Tailwind snippets are **not** drop-in components for Expo/React Native. Port concepts with native primitives.
6. Preserve user-approved design and existing flows. Make changes in small, testable increments; record test results accurately.
7. Respect dark/light modes, 44pt touch targets, reduced motion, responsive layouts, input errors, loading/empty states and keyboard accessibility.
8. For Chat On Steroids, restrict Workspace to approved project folders, avoid granting desktop/terminal capabilities globally, and obey provider limits.

## Project-specific priorities
- **ELOQ** — retain the approved Game First v1.2 design: QG, 1v1 Arena, instantly playable mini-games, Crew, Profile, casual adult/teen tone, clarity and dark/light modes. Learning should happen through play, not a course UI.
- **My Vidéo / motiongen-ai** — preserve the current Base44 workflow, video catalog, Timeline V1 model, voice and export flows. Prioritize a frictionless creation experience and transparent render/export progress.
- **FITAIA** — preserve identity/consistency of realistic avatars, user privacy and wellness-centered flows.
- **TMX TV** — preserve existing behavior; only use this catalog if the task requires UI; do not modify infrastructure/test code on design grounds.
- **New projects** — write a brief unique product style and navigation strategy before picking components.
