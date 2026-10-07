# Orbital Observatory — implementation QA

Reviewed 7 October 2026. Final result: **passed**.

## Comparison target and evidence

- Source visual truth: `design/reference.png`, the first mock selected by the user, 1487 × 1058 pixels.
- Implementation: `http://127.0.0.1:4173/`, captured in the Codex in-app browser. `design/qa/desktop-final.webp` is 1487 × 1058 pixels at a 1487 × 1058 CSS viewport, devicePixelRatio 1. No density scaling was needed.
- Matched state: dark theme, Experimental, Portishead selected, the same six sample entities and three seeds. Animation paused for comparison. Intentional differences: explicit sample label/copy, Make it yours, a pause control and one bookmark left by the live smoke test. The sample is not presented as a real API response.
- Combined full-view evidence: `design/qa/full-comparison.webp` (source left, implementation right). Focused comparisons: `design/qa/panel-comparison.webp` and `design/qa/controls-comparison.webp`. These were opened and inspected together, not reviewed from filenames or code alone.
- Responsive evidence: `design/qa/tablet-final.webp` (1024 × 909 full-page capture; CSS viewport 1024 × 900), `tablet-stacked.webp` (768 × 1399; viewport 768 × 1024), `mobile-live-final.webp` (390 × 1344; viewport 390 × 844), and `mobile-compact-final.webp` (320 × 1252; viewport 320 × 740). All use density 1; full-page heights include naturally scrollable content, not browser chrome.
- `design/qa/mobile-dialog-final.webp` shows the entire interest form at 390 px width. This full-page capture is 390 × 1344, taken with a tall 390 × 1248 CSS viewport; it is not an 844 px phone-viewport screenshot. Separately, at 390 × 844 the empty dialog measured 352 × 761 CSS px, remained inside the viewport, and the selected/search states used internal scrolling.

## Findings and comparison history

All actionable P0/P1/P2 findings below are resolved.

1. **P1 typography and background drift; P2 desktop overflow.** The first combined comparison (`qa/comparison-before.png`, local diagnostic) had narrow Instrument Serif letterforms, a dominant bright starfield and a 1087 px shell at a 1058 px viewport. Changed the display face to Georgia, reduced the raster backdrop opacity and shortened the system's height. Post-fix: `qa/comparison-revised.png`, then the final combined evidence. The shell now measures exactly 1487 × 1058; exploration controls fit.
2. **P2 compact orbital composition and label placement.** The generated orbital asset was more tilted/compact than the target and labels were all centered beneath bodies. Adjusted the real raster asset's rotation/size, planet sizes/positions and above/below label anchors. Final full-view comparison retains the target's solar-system hierarchy and 72.7% / 27.3% major-region split.
3. **P1 live labels crossing the detail panel; P2 description density.** Real Qloo book titles were much longer than sample labels (`qa/live-saved.jpg`). Applied bounded desktop ellipsis, two-line responsive labels, full accessible names/tooltips, smaller long-title headings and a three-line description preview. Full text remains in the detail dialog. Post-fix evidence: `qa/live-revised.jpg` and the tracked responsive live captures.
4. **P2 tablet caption collision and control position.** At 1024 px, a long label collided with the orbital caption and the control row exceeded the intended 900 px viewport. Moved the caption below labels, clamped outer planet anchors and reduced the field height. Post-fix DOM check put the control region inside the viewport with no horizontal overflow; `design/qa/tablet-final.webp` confirms separated labels/caption.
5. **P2 small secondary touch targets.** Increased Saved, motion, close, edit and feedback hit areas to at least 44 px. Removed left navigation padding on compact screens so its hit box no longer overlaps the wordmark. At 320 px, scrollWidth equals viewport width and the visible brand/action labels do not collide. Final compact capture confirms the arrangement.

## Required fidelity surfaces

- **Fonts/typography:** Georgia matches the source's wider editorial letterforms substantially better than the initial face. Inter is self-hosted for UI text. Heading hierarchy, subtitle/CTA wrapping and readable small labels checked in the focused panel/control comparisons. Long live text is intentionally bounded with full detail available.
- **Spacing/layout rhythm:** sidebar proportion, header, seed row, divider, exploration control and selected detail anatomy preserved. Desktop controls fit the source viewport. At 850 px and below, the detail panel stacks; tapping a planet scrolls its description into view. No horizontal overflow at 320, 390, 768, 1024 or 1487 px.
- **Colors/tokens:** dark navy `#070b14`, near-white text/CTA, amber sun and restrained lavender states follow the source. Muted copy, active indicators, hover and visible keyboard outlines remain distinguishable. No decorative CSS gradients replace artwork.
- **Image quality:** all nine assets are real raster images: background, orbits, sun and six bodies. Alpha is retained; edges remain clean at display sizes. WebP assets total approximately 675 KiB. Phosphor provides UI icons. No hand-drawn SVG/CSS substitutes for the source art.
- **Copy/content:** samples are explicitly labelled, live explanations are from the API, no invented affinity percentages or scientific orbit claims. Raw Qloo tag URNs become readable labels while the canonical value remains in the tooltip. Loading, empty, error, retry and successful-save text are distinct.

## Function and accessibility checks

Browser-tested real Qloo search for David Bowie, Radiohead and Björk; three-interest discovery; six live cross-category results; acknowledged Save and Saved dialog; a new Wild selection; one Gemini-backed intention; a validated three-step introduction; already-know feedback; and Escape closing dialogs. The search input receives focus when its dialog opens. Planet buttons retain full accessible names. System reduced-motion and paused animations are covered by component tests. Console error/warning checks returned none.

Final automated checks: 23 frontend tests, 137 backend tests (3 opt-in live tests skipped), 4 packaging tests, TypeScript, Ruff, formatting, production build and npm audit (0 reported vulnerabilities). A valid foreign-Origin write through the development proxy returned 403. Live browser checks are smoke tests, not proof of recommendation quality or production readiness.

## Follow-up polish and limits

P3: generated grain, atmospheric sun glow and individual orbital strokes are not pixel-identical to the mock. Small UI optical sizes and icon strokes can be tuned further. The source did not specify responsive layouts, so those are functional adaptations rather than 1:1 mobile clones. Georgia fallback rendering on other operating systems and real mobile soft keyboards were not tested.

Bookmarks are device-local; refreshing restores the labelled preview rather than session history. Production HTTPS hosting, API reverse proxy, shared quotas and session cleanup remain separate work. No deployment occurred in this pass.

Implementation checklist: selected art direction retained; all assets placed; core controls connected; real-provider smoke flow verified; responsive and keyboard states checked; earlier blocking findings fixed and re-compared.

final result: passed
