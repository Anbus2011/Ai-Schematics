# EZSchem — Schemdraw Wrapper for AI-Generated Schematics

## Project Overview

EZSchem is a Python wrapper module on top of Schemdraw that enables AI (Claude) to produce clean, human-readable circuit schematics from a simple netlist-style description. The core problem is that Schemdraw requires precise spatial reasoning (coordinates, anchor positions, wire routing, label placement) which LLMs are bad at. EZSchem abstracts that away — AI describes topology, EZSchem handles geometry.

## Architecture

```
AI describes circuit (netlist) → EZSchem wrapper → Schemdraw → PNG + SVG output
```

### Two Deliverables

1. **`ezschem/`** — Python package, installed alongside Schemdraw
2. **Skill file** (`SKILL.md`) — Teaches Claude how to use EZSchem correctly

## Design Constraints

- **Single-page schematics only**, up to ~30 components
- **Simple grid-based layout** — KISS. Power top, ground bottom, signal left-to-right
- **Wraps Schemdraw's built-in component library** — no custom symbols for now
- **Optional layout hints** — override auto-placement when needed
- **Output:** PNG (for AI verification) + SVG (for user, scalable/editable)

## Package Structure

```
ezschem/
    __init__.py        # Public API: draw(parts, nets, hints) → PNG/SVG
    components.py      # Type mapping + anchor aliases + component sizes
    parser.py          # Netlist parser + validation + circuit graph builder
    placer.py          # Grid layout algorithm (layered graph, transistor-aware)
    router.py          # Wire routing (L/Z-route) + occupancy grid + junction dots
    renderer.py        # Schemdraw drawing commands + label placement + power/ground symbols
```
Note: `orientation.py` and `labels.py` from the original plan were folded into
`placer.py` and `renderer.py` respectively — they weren't complex enough to justify
separate files.

Consumer API is simple — the package internals are invisible:
```python
import ezschem
ezschem.draw(parts, nets, hints={}, output="circuit.png")
```

## Module Details

### 1. Netlist Parser
- Accepts component list (name, type, value) and connection strings
- **Name resolution rule:** Any name in a net string that is a key in `parts` is a component reference. Any name NOT in `parts` is a named net node (e.g., `Vcc`, `GND`, `Vin`, `Vout`). Pin-qualified names like `Q1.C` reference a specific anchor on a component.
- **Power/ground nodes** (`Vcc`, `GND`, `Vdd`, `Vss`) are special: each occurrence spawns a **local power/ground symbol** at that connection point, rather than wiring everything back to a single shared node. This prevents rat's-nest wiring.
- Connection format uses chained strings describing signal paths:
  ```python
  parts = {
      "R1": ("res", "470"),
      "LED1": ("led",),
      "Q1": ("npn",),
  }
  nets = [
      "Vcc -> R1 -> LED1 -> Q1.C",
      "Q1.E -> GND",
      "Q1.B -> R2 -> Vcc",
  ]
  ```
- Parser builds an internal graph of components and connections
- **Validation:** Parser checks that all component references exist in `parts`, pin names are valid for the component type, and reports clear error messages for invalid netlists (critical for AI self-correction)

### 2. Grid Placer (`placer.py`)
- Assigns each component a (row, col) on a grid
- **Primary flow is vertical** (power top → ground bottom). Layers = rows, parallel branches = columns.
- Uses a **layered graph layout** algorithm (simplified Sugiyama):
  1. Build directed graph from net strings, classifying edges as **vertical** (collector/emitter/start/end) or **horizontal** (base/gate)
  2. Assign rows via longest-path from power-connected sources
  3. Components connected only by horizontal edges (e.g., base bias resistors) inherit the row of their horizontal neighbor
  4. Assign columns within each row using barycenter heuristic (two-pass: top-down then bottom-up for alignment)
- **Grid spacing:** `GRID_SPACING_X = 6.0`, `GRID_SPACING_Y = 5.0` (Schemdraw units)
- **Orientation rules (integrated, no separate solver):**
  - Two-terminal components (res, cap, ind, diode, led, sw): `orientation="down"` (vertical chain)
  - Transistors (npn, pnp, nmos, pmos): `orientation="right"` — their natural Schemdraw orientation already has collector/drain at top, emitter/source at bottom, base/gate to the left
- For hard cases, layout hints provide the escape valve

### 3. Wire Router (`router.py`)
- Orthogonal (right-angle) paths only — no diagonal wires ever
- **L-route first, Z-route fallback:** Try L-shaped (one bend) routing first; if the corner is occupied by a component, use Z-shaped (two bend) routing through a clear channel
- Uses `elm.Line().at().to()` for wire segments (not `.tox()`/`.toy()` — direct point-to-point is cleaner)
- Maintains an **occupancy grid** of component bounding boxes to avoid routing through component bodies
- **Junction dots:** Automatically inserts `elm.Dot()` at T-junctions where 3+ wire segment endpoints meet at the same point

### 4. Label Placement (integrated into `renderer.py`)
- Labels are positioned automatically with padding controlled by constants at the top of `renderer.py`:
  - `LABEL_PAD = 0.225` — gap between component body and ref/value label
  - `NET_LABEL_PAD = 0.5` — offset for net node labels (Vin, Vout) from connection point
  - `SUPPLY_LABEL_PAD = 0.3` — offset for power/ground labels (Vcc) from symbol
- **Schemdraw `loc` mapping for `.down()` elements is rotated:**
  - `loc='bottom'` = right side in drawing space
  - `loc='top'` = left side in drawing space
  - `loc='right'` = top (start) in drawing space
  - `loc='left'` = bottom (end) in drawing space
- **Per-component-type rules:**
  - Vertical two-terminal (res, cap, ind, sw): `loc='bottom'` (right side of body)
  - LEDs/diodes/zeners: `loc='top'` (left side — opposite from emission arrows)
  - Transistors (`.right()` orientation): `loc='right'` (right side, clear of collector/emitter wires)
- **Net node labels** (Vin, Vout): positioned above-left of the open dot connection point
- **Power labels** (Vcc): use Schemdraw's native `loc='right'` which gives natural padding

### 5. Layout Hints (Optional Overrides)
- Allow AI to proactively guide placement for circuits the auto-layout struggles with
- **Not a fallback for visual debugging** — the AI applies hints based on recognizing topology patterns (e.g., "this is a cross-coupled symmetric circuit") before ever rendering
- The SKILL file will teach the AI which patterns need hints and what hints to apply
- Syntax (planned):
  ```python
  hints = {
      "Q1": {"col": 0},
      "Q2": {"col": 2},
      "C1": {"row": 2, "orient": "right"},
  }
  ```
- Supported hint keys (planned): `row`, `col`, `orient`, `align_with`
- Hints are optional — auto-layout handles ~80% of common circuits without them
- **Known cases that need hints:**
  - Cross-coupled / symmetric circuits (astable multivibrator)
  - H-bridges
  - Circuits with feedback paths that create graph cycles

### 6. Component Value Display
- Values from `parts` dict (e.g., `"470"`, `"10uF"`) rendered as part of the component label
- Format: ref designator on one line, value on next — e.g., `"R1\n470Ω"`
- Units are passed through as-is (AI provides them in the `parts` value string)

### 7. Renderer (`renderer.py`)
- Calls Schemdraw drawing commands with calculated coordinates
- **Canvas sizing:** Automatically sizes drawing based on grid dimensions (rows × columns × grid spacing)
- Exports PNG at 150 DPI for verification
- Exports SVG for user delivery
- White background, clean line weights
- Named net nodes (Vin, Vout, etc.) rendered as text labels at their connection points

## Skill File (`SKILL.md`)

The skill file teaches Claude how to use EZSchem. Contents:

1. **When to use** — any request for a circuit schematic/diagram
2. **Component type names** — mapping of short names to Schemdraw elements:
   - `res` → Resistor
   - `cap` → Capacitor
   - `npn` → BjtNpn
   - `pnp` → BjtPnp
   - `nmos` → NFet
   - `pmos` → PFet
   - `led` → LED
   - `diode` → Diode
   - `zener` → Zener
   - `ind` → Inductor
   - `opamp` → Opamp
   - `sw` → Switch
   - etc.
3. **Anchor naming conventions** per component type:
   - EZSchem uses **short aliases** mapped to Schemdraw's real anchor names
   - Resistors/caps/inductors: `.p` / `.n` (or `.start` / `.end`) → Schemdraw `.start`, `.end`
   - BJTs: `.B`, `.C`, `.E` → Schemdraw `.base`, `.collector`, `.emitter`
   - MOSFETs: `.G`, `.D`, `.S` → Schemdraw `.gate`, `.drain`, `.source`
   - Op-amps: `.in1`, `.in2`, `.out` → Schemdraw `.in1`, `.in2`, `.out` (same names)
   - Diodes/LEDs: `.A`, `.K` → Schemdraw `.start`, `.end` (anode=start, cathode=end)
   - The mapping layer in `ezschem.py` translates short names to real Schemdraw anchors
4. **Net string syntax** — how to write connection chains
5. **Layout hint syntax** — how to override placement
6. **Common circuit examples** — copy-paste templates:
   - Voltage divider
   - LED + resistor
   - Common-emitter amplifier
   - Astable multivibrator
   - H-bridge
   - Op-amp inverting/non-inverting
   - Voltage regulator (LDO)
   - RC/LC filter
7. **Troubleshooting** — common issues and fixes

## Build Status

### Completed
1. **`components.py`** — type mapping, anchor aliases, component sizes, power/ground detection
2. **`parser.py`** — netlist parser, auto-pin assignment for two-terminal components, pin validation with clear error messages
3. **`placer.py`** — layered graph layout with vertical/horizontal edge classification, transistor-aware row/column assignment, barycenter heuristic
4. **`router.py`** — L-route with Z-route fallback, occupancy grid from component bounding boxes, junction dot detection
5. **`renderer.py`** — Schemdraw rendering, label placement with per-type rules, local power/ground symbols, net node labels, wire drawing
6. **`__init__.py`** — public `draw()` API

### Remaining
7. **Layout hints implementation** — parse hint dict and apply row/col/orient overrides in placer
8. **Skill file (`SKILL.md`)** — teach Claude how to use EZSchem, including when to apply hints
9. **Placer improvements for complex topologies:**
   - Symmetry detection for cross-coupled circuits (astable multivibrator)
   - Horizontal layout mode for circuits that read better left-to-right
   - Better handling of graph cycles (cross-coupling breaks topological sort)
   - **Base-connected components should be placed on the base side of transistors** (left, where the pin faces), not in distant columns that force wires through other components. In the astable, R3/R4 are placed to the right of Q1/Q2 but Q1/Q2's base pins face left — wires from R3/R4 must cross through Q2/Q1 bodies to reach the base. This is a placer problem, not a router problem.
10. **Wire routing improvements** — router now has segment-level collision detection and accurate occupancy grid with transistor alignment. Remaining issue: router cannot fix wires that *must* cross components due to bad placement (see item 9).
11. **Transistor alignment** — renderer has a post-pass to shift components connected to collector/emitter by 0.75 units; this works but is fragile if Schemdraw changes BJT geometry

## Dependencies

- Python 3.10+
- `schemdraw` (pip install schemdraw)
- `matplotlib` (schemdraw dependency, used for PNG rendering)

## Schemdraw Key Patterns (Reference for Development)

### What works well:
- Component symbols are clean and publication-quality
- Anchor points on components are reliable
- Sequential drawing along a path is straightforward
- `.at()` for jumping to specific positions
- `.label()` for component annotation

### What causes problems (why this wrapper exists):
- No auto-routing — wires go wherever you tell them, including through components
- `.to()` draws diagonal lines — must use `.tox()` + `.toy()` for orthogonal routing
- Label placement is manual — no collision detection
- No netlist input — everything is positional/sequential
- Complex cross-coupled circuits require careful drawing order planning
- Flipped transistors swap collector/emitter anchor positions

### Default component orientations:
- Resistors, capacitors, inductors draw **horizontally** by default (3 units long)
- BJTs and MOSFETs draw **vertically** by default when using `.right()`: collector/drain at top (+Y), emitter/source at bottom (-Y), base/gate to the left (at the `.at()` position)
- Op-amps draw horizontally (inputs left, output right)
- **For vertical power→ground circuits:** use `.down()` for two-terminal components, `.right()` for transistors (their natural vertical orientation)

### Schemdraw label `loc` behavior (CRITICAL — rotates with element direction):
- For `.right()` elements: `loc='top'` = above, `'bottom'` = below, `'left'` = start, `'right'` = end
- **For `.down()` elements, `loc` rotates 90°:**
  - `loc='bottom'` → **right side** in drawing space (use for labels on vertical components)
  - `loc='top'` → **left side** in drawing space (use for LEDs/diodes to avoid arrows)
  - `loc='right'` → **top** (start) in drawing space
  - `loc='left'` → **bottom** (end) in drawing space
- The `ofst` parameter adds padding between the component body and the label text
- `ofst=0.225` provides good clearance without excessive spacing

### Critical Schemdraw gotchas:
- `elm.BjtNpn().flip()` mirrors the component — collector and emitter anchors swap sides
- `.right(distance)` DOES accept a distance argument in Schemdraw 0.22 — e.g. `.right(6)` sets element length/direction
- Labels with `\n` in them create multi-line labels (useful for ref + value)
- `elm.Dot()` creates a filled junction dot, `elm.Dot(open=True)` creates an open circle (for terminals)
- `elm.Ground()` always draws downward from its connection point
- `elm.Vdd()` always draws upward from its connection point — `loc='right'` with `ofst` gives natural label padding
- LED/Diode elements have emission/direction arrows that extend to one side — place labels on the **opposite** side to avoid overlap

## Tested Circuits

### Works well (auto-layout)
- **LED + resistor** — `Vcc -> R1 -> LED1 -> GND` (simple vertical chain)
- **RC low-pass filter** — `Vin -> R1 -> C1 -> GND` (vertical chain with net label)
- **Voltage divider** — `Vcc -> R1 -> R2 -> GND`
- **Common-emitter amplifier** — multi-branch circuit with BJT, base bias, collector load, emitter resistor

### Needs layout hints (auto-layout produces messy output)
- **Astable multivibrator** — cross-coupled symmetric topology breaks topological sort; base bias resistors placed in wrong columns; cross-coupling capacitors should be horizontal but render vertical. Will need hints to place Q1/Q2 in mirrored columns.

## Notes

- This project was planned in Claude.ai conversation and is being built in Claude Code
- Circuit-Synth + KiCad MCP was evaluated as an alternative path but deferred — EZSchem is for quick standalone schematic images, not full EDA project generation
- If EZSchem works well, a follow-up project could bridge it to KiCad export via kicad-sch-api
