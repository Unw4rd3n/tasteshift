# Orbital Observatory assets

Visual target: `reference.png`, the user's first selected direction. Nine separate raster assets were created with the built-in image generator using that image as the visual reference: a deep navy starfield, thin translucent orbital tracks, a warm amber sun, and violet, ice-blue, rust, cratered grey, ocean-blue and banded Jupiter-like planets. Each body is independently selectable; no UI text is baked into the artwork.

Original PNGs are preserved locally under `source-assets/`. Served WebP copies are under `public/assets/`, retaining alpha. `scripts/optimize-assets.mjs` performs encoding/resizing only (512 px bodies, full-width background/orbits), using Sharp. To rerun, provide an installed Sharp package path or install Sharp separately for this tooling step. All nine served files total approximately 675 KiB. Source artwork is not shipped in the web build.

UI text uses self-hosted [Inter](https://github.com/rsms/inter) (SIL Open Font License); display text uses the browser's Georgia serif with Times fallback to match the selected mock's wider letterforms. Icons use [Phosphor](https://github.com/phosphor-icons/react) (MIT), rather than hand-drawn replacements. Decorative images have empty alt text; each planet button has the full entity name and category as its accessible label.

Animation is limited to transform/opacity: restrained floating bodies, slow orbital drift, a breathing sun and mouse-only bounded parallax. The pause control, document visibility and system reduced-motion setting stop it.
