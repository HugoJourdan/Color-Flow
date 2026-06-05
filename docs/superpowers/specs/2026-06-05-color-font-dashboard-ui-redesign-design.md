# Color Font Dashboard — UI Redesign Design

Date: 2026-06-05
Status: Approved (design); ready for implementation planning
Branch: `feature/colorflow-rainbow-merge`

## Context

The Color Font Dashboard (`Color Flow.glyphsPalette/Contents/Resources/colorflow_dashboard.py`)
generates an HTML progress report opened from the palette's Action popover. A prior
pass made its **counts match the palette exactly** (mode-aware via the shared
`colornames` counting), added light/dark theming, accessibility, an Overall-totals
section, and a per-glyph heatmap. That data/counting work is correct and stays.

The current **presentation** is a static, GitHub-styled, table-driven page with no
interactivity. The user wants a **complete UI overhaul to a contemporary look** and
improved UX. This spec defines that redesign.

## Goals

- A contemporary "pro-tool" aesthetic (Direction A: dark-default, dense, precise —
  Linear/Vercel/Raycast register), with a full light theme.
- Fully interactive, delivered as a **single self-contained offline `.html`** with
  inline CSS + inline JS and **zero network/dependencies**.
- Interactions: glyph search, filters, step sorting, master tabs + a compare matrix,
  theme toggle, an actionable heatmap, animate-on-load.
- Preserve correctness: counts still match the palette; the snapshot / changed-since-
  last-run behaviour is retained.

## Non-goals

- No change to the counting/data semantics shipped previously (`master_counts`,
  `uncolored_count`, `build_master_glyph_colors`, mode detection, snapshot storage).
- No change to `plugin.py` / `colornames.py` / `settings_panel.py`.
- No build step, bundler, or third-party JS/CSS. No web framework.
- Not a server; the report remains a file opened in the browser.

## Architecture

The split becomes **Python = data model + shell; JavaScript = render + interaction**.

### Python responsibilities

1. Reuse the existing data layer unchanged to compute, per font: mode (`free_mode`),
   counting `order` (`_meaning_and_none` → `load_meaning` keys), visible steps +
   labels (`display_from_meaning`), per-master per-glyph keys
   (`build_master_glyph_colors`), per-master counts (`master_counts`), uncoloured
   tallies (`uncolored_count`), and changes (`compute_changes`, snapshot helpers).
2. Serialize a single **model** object (schema below) to JSON.
3. Emit a small HTML **shell**: `<head>` + inline `<style>` (the design tokens +
   component CSS) + the model embedded in `<script type="application/json"
   id="cfd-model">` + the inline app `<script>` + a `<noscript>` notice.

The heavy per-row/table HTML building currently in Python (`build_master_section`,
`_master_table`, `_count_row`, `build_overall_totals`, `build_heatmap_section`,
`_summary_bar`, `_change_log`, `build_sidebar`) is **removed**; that DOM is built by
JS from the model. `main()` keeps its flow (guard empty font, write file via
`pathlib`, open via `Path.as_uri()`).

### Model JSON schema (compact; glyph names stored once)

```jsonc
{
  "family": "Acme Sans",
  "fileName": "Acme.glyphs",
  "version": "2.5",
  "generated": "2026-06-05",            // from datetime passed in (testable)
  "mode": "step",                        // "step" | "free"
  "glyphTotal": 22,                      // len(font.glyphs), per master
  "order": ["8","4","6","3","0"],        // str counting order (incl. hidden slots)
  "steps": [                             // visible display rows, in order
    {"key": 8, "label": "Outline corrected"},
    {"key": 4, "label": "Anchors placed"}
  ],
  "noneLabel": "🫥 None",
  "glyphNames": ["A","B","C"],           // once, in glyph order
  "masters": [
    {
      "id": "m1", "name": "Regular",
      "keys": [8,4,-1],                  // per glyph, aligned to glyphNames (-1 = none)
      "counts": {"8":14,"4":10,...},     // str-keyed, matches palette
      "uncolored": 6
    }
  ],
  "changes": { "m1": { "B": [-1, 4] } }  // {masterId: {glyph: [oldKey,newKey]}}
}
```

JS derives everything else: per-step `% = counts[key]/glyphTotal`; per-master
`started = glyphTotal - uncolored`, step-mode `completion = counts[order[-1]]`;
overall = aggregate over masters (`grandTotal = glyphTotal * masters.length`);
compare matrix from `masters[].counts`; heatmap/search from `glyphNames` + `keys`.

### JavaScript responsibilities (vanilla, inline)

- Parse the embedded model; render header, toolbar, overall hero, tabs/compare,
  per-master step rows, heatmap, changes panel.
- State: active master, view (tabs|compare), search query, filters (unfinished-only,
  active step), sort (workflow|progress), theme. Held in a small state object; UI
  re-renders the affected region on change. Theme persists to `localStorage`.
- Build DOM with correct ARIA (`role="progressbar"` + `aria-valuenow/min/max`,
  `<th scope>`, accessible names for swatches/cells, focus styles).

## UI / views

- **Header (sticky):** family · file · version · `Mode · Step|Free` · theme toggle.
- **Toolbar (sticky):** search input (`/` to focus); filter chips (Unfinished only;
  jump-to-step); sort toggle (workflow ↔ progress); Compare toggle.
- **Overall hero:** big `% complete` + `% started` + segmented bar + per-step legend.
  In free mode the headline is the labelled share (completion ≡ started).
- **Tabs (default view):** one master in focus; toolbar state applies to it. Tab strip
  scrolls for many masters.
- **Compare (toggle):** matrix — steps as rows, masters as columns, each cell the
  step's % for that master; horizontal scroll past ~5 masters.
- **Per-master step rows:** colour dot · label · thin bar · `count/total` · `%`; a ✓
  when a step reaches 100%. Bars are cumulative in step mode, exact in free mode
  (unchanged semantics).
- **Per-glyph heatmap (collapsible):** grid of cells for the focused master, glyph
  order, default **unfinished-only**, cap 500 + "+N more". Hover → `glyph — colour`
  tooltip; click → copy glyph name (toast confirm). Honours search/filter.
- **Changed since last run:** panel listing per-glyph old→new colour, with accessible
  swatch labels.

## Theming tokens

Dark `:root` is the default (Direction A palette). `@media (prefers-color-scheme:
light)` provides the light flip, and the theme toggle overrides via a `data-theme`
attribute on `<html>` (persisted). Tokens: `--bg/--surface/--surface-2/--border/
--text/--muted/--accent/--track/--swatch-outline`, the 12 `--c0..--c11` swatch hues
(identical in both themes) + `--c-none` hatch, plus spacing/type/radius ramps. Accent
(`--accent`, default `#6e7bff`) is a single rebrandable variable.

## Accessibility

- Landmarks (`<header>`, `<nav>`, `<main>`), `<html lang="en">`.
- Progress elements: `role="progressbar"` + aria values + label.
- Tables (compare/changes): `<th scope>`, `<caption>`.
- Swatches/cells: non-colour cue via adjacent text or `title`/`aria-label`
  (attribute text escaped for quotes).
- Visible focus ring; `prefers-reduced-motion` disables the load animation.
- Tooltips are native `title` plus `aria-label`; the click-to-copy control is a real
  focusable button per cell (or delegated keyboard handling) so it is operable.

## File output

Single `.html` written to the temp dir (filename unchanged), opened with
`Path(out_path).as_uri()`. Inline `<style>` + `<script>` only; the embedded model is
the sole data source. `<noscript>`: "This report needs JavaScript; re-open in a modern
browser." (Acceptable per the chosen fully-interactive direction.)

## Testing

- **Python (pytest):** the model builder is pure and unit-tested — assert structure,
  compact glyph-name-once layout, str-keyed counts equal `colornames.counts_from_colors`
  / `single_counts_from_colors` (parity, both modes, incl. the hidden-label +
  non-numeric-order regression), changes shape, and the empty-font guard. Assert the
  emitted HTML embeds the JSON (`id="cfd-model"`), the `<style>`, the app `<script>`,
  `<noscript>`, both theme blocks, and that JSON is HTML-safe inside the script tag
  (e.g. `</script>` / `<` sequences can't break out).
- **JS / visual:** a build-time harness renders a sample model to `sample.html`;
  verified in-browser (light/dark, search/filter/sort, tabs↔compare, heatmap
  hover/click-copy, keyboard). Not unit-tested in Python.
- ruff / pyright / pytest stay green; `uv run pytest -n auto`.

## Migration / impact

- `colorflow_dashboard.py`: replace the HTML-builder functions with `build_model`
  (pure) + `embed_model`/`render_shell` + the inline CSS/JS string constants; keep the
  data-layer + snapshot functions. Update `build_html`/`main` wiring.
- `tests/test_colorflow_dashboard.py`: drop the per-row HTML-builder assertions; add
  model + embedding tests (parity tests largely reused, retargeted at the model).
- README: refresh the dashboard section/screenshot to the new UI.
- No other modules change.

## Risks

- **JSON-in-HTML injection/escape:** the model contains glyph names / labels; it must
  be embedded so no value can terminate the `<script>` (escape `<`/`>`/`&` or `</`
  sequences in the serialized JSON). Covered by a test.
- **Large fonts:** thousands of glyphs × many masters → model size. Mitigated by
  storing names once + per-master small-int key arrays; heatmap render capped.
- **JS-only:** no-JS users get the `<noscript>` notice (accepted trade-off).

## Open questions

None — design approved. Accent colour defaults to `#6e7bff`; change the single
`--accent` token to rebrand.
