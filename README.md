# AZ Colorflow

**AZ Colorflow** (formerly Color Flow) is a Glyphs palette plugin — for **Glyphs 3 and Glyphs 4** — that turns the twelve native **Layer Color Labels** into a customizable, gamified workflow. Assign a meaning to each colour, tick the steps off as you work, and watch colour-coded progress counts fill as your font moves from *outline* to *done*. A built‑in, offline **progress report** gives you a font‑wide picture — a completion ring, coverage, a per‑glyph heatmap, a save‑by‑save timeline, and a Time Machine to replay your progress.

<img src="img/report-overview.png" width="900" alt="AZ Colorflow report — overview">

> The wide screenshots above and below come from the plugin's **HTML report**. Screenshots of the palette UI itself are coming soon.

---

# Glyph Color 🆚 Layer Color

In Glyphs, color labels can be defined on two levels — **Glyph** and **Layer** — in one of twelve predefined colors.

* **Set Glyph Color** — control‑click / right‑click a glyph.
* **Set Layer Color** — right‑click a glyph while holding Option.

Glyph Color spans the whole glyph cell. Layer Color is drawn on the right half of the cell when a Glyph Color is also set, or across the whole cell with a cut‑out in the top‑left when no glyph color is set.

| Glyph Color | Layer Color | Glyph + Layer Color |
| :---: | :---: | :---: |
| <img src="img/Glyph-Color-Label.png" width="100"> | <img src="img/Layer-Color-Label.png" width="100"> | <img src="img/Glyph+Layer-Color-Label.png" width="100"> |

AZ Colorflow reads the **Layer Color** to track the progress of each layer, for example:

* 🟣 → Outline corrected
* 🟢 → Anchors placed
* 🔵 → Spacing set
* 🟡 → Ready to export

> **Tip** — since Layer Color is the one that matters here, AZ Colorflow can swap Glyphs' click routing: with **Swap Option color routing** enabled (*Glyphs → Settings → AZ Colorflow → Behaviour*), a plain right‑click sets the **Layer** Color and Option‑click sets the Glyph Color — the inverse of stock Glyphs.

---

# The colorNames.txt file

AZ Colorflow stores the meaning of each colour as `colorName=meaning` lines. The labels are resolved in this order:

1. **Inside the font** — labels stored in the `.glyphs` file itself (`font.userData`) win, so a shared font shows the same workflow for every collaborator, no sidecar file needed. When present, edits keep it in sync.
2. **Next to the source** — a `colorNames.txt` in the same folder as the current `.glyphs` file, so the labelling can travel with the project.
3. **Shared** — `colorNames.txt` in Glyphs' *Application Support* `info` folder (resolved from the running app, so it works in both Glyphs 3 and Glyphs 4).

You don't have to create anything: on first run the plugin writes a default `colorNames.txt` with all twelve colours. The format is one `colorName=meaning` per line (whitespace around the `=` is tolerated; unknown colour names are skipped):

```
red=Step 1
orange=Step 2
brown=Step 3
yellow=Step 4
lightGreen=Step 5
darkGreen=Step 6
lightBlue=Step 7
darkBlue=Step 8
purple=Step 9
magenta=Step 10
lightGray=Step 11
charcoal=Step 12
```

---

# Customize

The point of AZ Colorflow is that the **meaning and order** of colours are yours. The comfortable way is the plugin's pane in **Glyphs → Settings → AZ Colorflow**:

* **Double‑click a name** to rename it in place.
* **Click the swatch** to recolour the label (changes Glyphs' label colour itself).
* **Click the eye** to hide a colour — it keeps its name, it just leaves the workflow.
* **Drag rows** to reorder the workflow steps; hidden rows stay pinned below.
* The **reload icon** next to the title resets colours, names and order to the defaults.

Every edit is written back to `colorNames.txt` (or into the font, if it stores its labels in‑file) and broadcast live, so the palette, the report and the Font Glyph Order sections all relabel immediately.

The file also stays hand‑editable: reorder by moving lines, hide a colour by leaving its meaning blank or commenting the line out with `#`:

```
#red=Red
#orange=Orange
purple=Outline corrected
lightGreen=Anchors placed
lightBlue=Spacing set
yellow=Ready to Export
#magenta=Magenta
```

Resulting workflow in the palette:

* 🟣 → Outline corrected
* 🟢 → Anchors placed
* 🔵 → Spacing set
* 🟡 → Ready to Export

---

# How it works

A layer's **colour is its current step**: the palette shows your visible steps in order, and a layer sitting at a colour counts as having completed every step up to and including it. Nothing extra is stored in your glyphs — the native Layer Color is the single source of truth, so the palette always agrees with the Font View.

In the palette, each row shows a step's label and a live **count** of the glyphs currently at exactly that step (non‑exporting glyphs never count). With glyphs selected, the rows they have reached are highlighted.

* **Set a step** — right‑click the selection and pick the step from the **Color Flow** submenu (or *Clear colour*); or just set the Layer Color natively.
* **Review a step** — **double‑click a palette row** to open exactly that step's glyphs in a new Edit tab and walk through them.
* **Header extras** — the palette's section header shows a mini colour‑progress bar while collapsed, and the **report button** while expanded.

A short multi‑slide tour introduces all of this the first time the plugin runs.

### Shortcuts

The palette registers a native **Jump to next color glyph** command that opens the next glyph that still needs work (its layer colour is not the final step). Assign it a key in *Glyphs → Settings → Shortcuts* (search "AZ Colorflow") — no extra install needed.

The same jump is also available as a script: install **"Color Flow Shortcut"** from *Window → Plugin Manager* and reload the scripts folder with `⌥ ⇧ ⌘ Y`.

---

# The progress report

A contemporary, **fully offline** report for the whole font, opened from the **report button** in the palette's header. It is a single self‑contained HTML file — no internet, no install — that you can keep or share. A progress sheet shows the build, and the report **opens automatically** in your browser when it's done.

Everything it shows matches the palette exactly: same glyphs, same Layer Color source, same counting.

### Progress at a glance

The Overview greets you with a big completion **donut ring**, tiled with your colour shares, next to a clickable colour legend — click a colour to focus its glyphs. A disc tower on the left holds one disc per master: click one to focus that master's own ring, stacked colour bar and cards. A *Furthest along* leaderboard and a this‑week card round out the global view.

<img src="img/report-progress.png" width="820" alt="Completion ring with stacked progress bar and legend">

### Coverage

How your colours are spread **by category** and **by writing system / script**, each script shown as a sample‑glyph card.

<img src="img/report-coverage.png" width="820" alt="Coverage by category and by script">

### Per‑glyph heatmap

Every glyph drawn as its own letterform, tinted by the step it's currently on. Hover a glyph for its step journey; click to open it in Glyphs. A Before/After switch flips the whole grid between the previous run and now.

<img src="img/report-heatmap.png" width="820" alt="Per-glyph heatmap for one master">

### Timeline

Completion over time, one point per save (or bucketed by time), with duration presets, a draggable range navigator, a this‑week digest, and per‑category and per‑script lanes. Focusing a master turns the graph into its per‑colour breakdown. For git‑tracked fonts the Timeline also lists **Shape changes** — glyphs whose outlines changed, drawn as onion‑skin overlays — and a *touched after done* watch list.

<img src="img/report-trend.png" width="820" alt="Completion over time">

The same card flips between the **Graph** and an **activity calendar** — click any day to jump the whole report to it:

<img src="img/report-calendar.png" width="820" alt="Activity calendar in the Timeline card">

### Time Machine

Replay your font's colouring moment by moment. Click anywhere on the Timeline chart — or a dot on the **Versions** line above a master's card — and the ring, bars, coverage, heatmap and lanes all fade back to the colour state at that moment.

<img src="img/report-scrubber.png" width="820" alt="Time Machine — pick a past moment and the whole report follows">

> **History, automatically** — a snapshot is recorded into the font's own data at **every save**, so the timeline travels with the file. And if your `.glyphs` / `.glyphspackage` lives in a **git repository**, AZ Colorflow additionally reconstructs the history straight from your past commits (capped to the 300 most recent). It runs automatically for git‑tracked fonts and is incremental, so only the first run does the heavy lifting.

### Also

* **Light & dark** — follows your system, with a one‑click toggle.
* **Export** — as **PDF** (a full printable report with a contents page), or the data as **CSV / JSON**.
* **Changed since last run** — glyphs whose colour changed since the previous report; that comparison snapshot lives in Glyphs' preferences, never in your `.glyphs` file.

---

# Font Glyph Order

AZ Colorflow can reorder the **Font View** into labelled colour sections, using the same `colorNames.txt` labels and order. Toggle it from **File → AZ Colorflow: Font Glyph Order** (a checkmark shows the state) or the checkbox in *Glyphs → Settings → AZ Colorflow*.

It is **non‑destructive**: your original glyph order is backed up when you enable it and restored when you disable it. The "None" bucket (glyphs with no colour) is always placed last.

> This feature merges the former **Rainbow FontView** plugin into AZ Colorflow. If you still have the standalone *Rainbow FontView* plugin installed, **disable or remove it** — otherwise both will fight over the Font View order. AZ Colorflow warns you once if it detects the old plugin.

---

# Install

Install **AZ Colorflow** (and optionally **Color Flow Shortcut** for the script version of the jump shortcut) from **Window → Plugin Manager**, then restart Glyphs. A default `colorNames.txt` is created for you on first run (see *The colorNames.txt file*).

---

*Thanks to Gor Jihanian ([@gorjious](https://github.com/gorjious)) for his contribution.*
