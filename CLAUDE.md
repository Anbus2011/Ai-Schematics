# EZSchem — AI-Friendly Circuit Schematic Generator

## Project Overview

EZSchem enables AI (Claude) to produce clean, human-readable circuit schematics from a simple netlist-style description. The AI describes topology using `parts`/`nets` dicts, EZSchem translates to Yosys JSON and renders via netlistsvg (Eclipse Layout Kernel) to SVG.

## Architecture

```
AI describes circuit (parts/nets) → translator.py → Yosys JSON → netlistsvg (ELK) → SVG
```

### Two Deliverables

1. **`ezschem/`** — Python package (pip-installable)
2. **MCP server** (planned) — Exposes `draw_schematic` tool for Claude Desktop
3. **Skill file** (`SKILL.md`, planned) — Teaches Claude the parts/nets syntax and circuit recipes

## Design Constraints

- **Single-page schematics only**, up to ~30 components
- **Layout is fully automatic** — ELK handles placement, routing, and junction dots
- **Output:** SVG only (clean, web-ready, scalable)
- **Dependencies:** Python 3.10+, Node.js (for netlistsvg/ELK)

## Package Structure

```
ezschem/
    __init__.py        # Public API: draw(parts, nets) → SVG path
    components.py      # Type mapping + anchor aliases + power/ground detection
    parser.py          # Netlist parser + validation (shared with translator)
    translator.py      # parts/nets → Yosys JSON + netlistsvg subprocess
    analog_skin.svg    # Auto-downloaded and patched skin (gitignored)
    placer.py          # [LEGACY] Custom Sugiyama placer — no longer imported
    router.py          # [LEGACY] Custom L/Z router — no longer imported
    renderer.py        # [LEGACY] Schemdraw renderer — no longer imported
```

Consumer API:
```python
import ezschem
ezschem.draw(parts, nets, output="circuit.svg")
```

## Rendering Engine: netlistsvg

### Why we pivoted (from custom Schemdraw placer)
The custom `placer.py` used a Sugiyama layered graph algorithm that failed on:
- **Cyclic topologies** (astable multivibrators — cross-coupling breaks topological sort)
- **Directional pin alignment** (base-connected components placed on wrong side of transistors)
- **Wire crossings** through component bodies (router can't fix bad placement)

netlistsvg uses the Eclipse Layout Kernel (elkjs) which handles all of these natively.

### How the pipeline works
1. `to_yosys_json(parts, nets)` — translates parts/nets into Yosys JSON format
2. JSON written to temp file alongside output
3. `npx netlistsvg input.json -o output.svg --skin analog_skin.svg` called via subprocess
4. SVG returned

### Skin file (`analog_skin.svg`)
- Auto-downloaded from netlistsvg GitHub on first run, cached in `ezschem/`
- Patched to add `nmos`/`pmos` aliases on the NPN/PNP transistor blocks
- Contains standalone NMOS/PMOS symbol definitions (not yet matched by netlistsvg — alias approach is the working fallback)
- **Key discovery:** netlistsvg matches cells by `<s:alias>` values, NOT by `s:type` attributes

### Skin alias mapping (ezschem type → skin alias)
| ezschem | skin alias | skin s:type | ports |
|---------|-----------|-------------|-------|
| `res` | `r_v` | `resistor_v` | A, B |
| `cap` | `c_v` | `capacitor_v` | A, B |
| `ind` | `l_v` | `inductor_v` | A, B |
| `diode` | `d_v` | `diode_v` | +, - |
| `led` | `d_led_v` | `diode_led_v` | +, - |
| `zener` | `d_sk_v` | `diode_schottky_v` | +, - |
| `npn` | `q_npn` | `transistor_npn` | C, B, E |
| `pnp` | `q_pnp` | `transistor_pnp` | C, B, E |
| `nmos` | `nmos` | (alias on `transistor_npn`) | C, B, E |
| `pmos` | `pmos` | (alias on `transistor_pnp`) | C, B, E |
| `opamp` | `opamp` | `opamp` | +, -, OUT |
| `sw` | `r_v` | `resistor_v` | A, B (stand-in) |

### Pin mapping (ezschem pin → skin port)
- Passives: `start` → `A`, `end` → `B`
- Diodes/LEDs: `start` → `+`, `end` → `-`
- BJTs: `collector` → `C`, `base` → `B`, `emitter` → `E`
- FETs: `drain` → `C`, `gate` → `B`, `source` → `E` (reuses BJT port layout)
- Op-amp: `in1` → `+`, `in2` → `-`, `out` → `OUT`

## Translator Details (`translator.py`)

### Net ID allocation
- Uses union-find to assign unique integer IDs to connected nets
- **Chain semantics:** `"A -> R1 -> B"` means A connects to R1.start, R1.end connects to B (two-terminal pass-through)
- **Explicit pins:** `"Q1.D"` connects only the drain pin (no pass-through)
- **Supply nets are local:** Each `Vcc`/`GND` occurrence spawns a separate cell attached to the adjacent component's net — prevents global short-circuit

### ELK direction hints
- `"elk.direction": "DOWN"` injected into `attributes` for vertical components (`r_v`, `c_v`, `l_v`, `diode_v`, `vcc`, `gnd`)
- The skin file also sets global `org.eclipse.elk.direction="DOWN"`

### Module ports
- Non-supply named nets (Vin, Vout, STO_A, MOTOR_OUT) become module-level ports
- Heuristic: names containing "OUT" get `direction: "output"`, others get `"input"`

## Netlist Parser (`parser.py`)

Shared between the old Schemdraw pipeline and the new netlistsvg pipeline.

- **Name resolution:** Any name in `parts` dict is a component reference. Any name NOT in `parts` is a named net node.
- **Power/ground nodes** (`Vcc`, `GND`, `Vdd`, `Vss`) spawn local symbols at each occurrence.
- **Auto-pin assignment:** Two-terminal components referenced without a pin get `start`/`end` assigned in order of use.
- **Validation:** Clear error messages for unknown types, invalid pins, missing components.

## Component Types (`components.py`)

```python
COMPONENT_TYPES = {
    "res", "cap", "ind", "diode", "led", "zener",
    "npn", "pnp", "nmos", "pmos", "opamp", "sw",
}
```

### Anchor aliases per type
- Two-terminal (res, cap, ind, sw): `.p`/`.n`, `.start`/`.end`
- Diodes/LEDs: `.A`/`.K` (anode/cathode), plus `.start`/`.end`
- BJTs: `.B`, `.C`, `.E`
- MOSFETs: `.G`, `.D`, `.S`
- Op-amp: `.in1`, `.in2`, `.out`, `.vd`, `.vs`

## Build Status

### Completed
1. **`components.py`** — type mapping, anchor aliases, power/ground detection
2. **`parser.py`** — netlist parser, auto-pin assignment, pin validation
3. **`translator.py`** — Yosys JSON translation, net ID allocation (union-find), per-type pin mapping, local supply symbols, ELK hints, skin management, netlistsvg subprocess
4. **`__init__.py`** — public `draw()` API using netlistsvg backend
5. **Custom skin** — NMOS/PMOS aliases on NPN/PNP blocks (working), standalone NMOS/PMOS SVG blocks (not yet matched by netlistsvg)

### Remaining
6. **MCP server** — thin wrapper exposing `draw_schematic(parts, nets)` tool for Claude Desktop
7. **Skill file (`SKILL.md`)** — teaches Claude the parts/nets syntax, component types, pin aliases, and circuit topology recipes
8. **Circuit recipes** — topology templates for common circuits (voltage divider, LED+resistor, common-emitter, astable multivibrator, H-bridge, op-amp configs, filters)
9. **NMOS/PMOS distinct symbols** — standalone skin blocks exist but netlistsvg doesn't match them; currently renders as NPN/PNP via alias. Need to investigate netlistsvg's skin parser to get `s:type` matching working, or post-process the SVG.
10. **Cleanup legacy modules** — `placer.py`, `router.py`, `renderer.py` are no longer imported; can be removed once we're confident in the new pipeline
11. **PNG output** — netlistsvg only outputs SVG. If PNG is needed, add a post-conversion step (e.g., cairosvg or Inkscape CLI).

## Dependencies

- Python 3.10+
- Node.js (LTS) — for `npx netlistsvg`
- `netlistsvg` npm package (auto-downloaded by npx on first run)

### Python packages (for legacy pipeline, may be removable)
- `schemdraw` — only used by legacy placer/router/renderer
- `matplotlib` — schemdraw dependency

## Tested Circuits

### Works well (netlistsvg/ELK)
- **LED + resistor** — `Vcc -> R1 -> LED1 -> GND` (simple vertical chain)
- **STO (Safe Torque Off)** — two NMOS in series with pull-down resistors, separate enable signals
- **Astable multivibrator** — cross-coupled NPN topology with coupling capacitors (previously broken with custom placer)

### Not yet tested
- Common-emitter amplifier
- Op-amp inverting/non-inverting
- H-bridge
- Voltage regulator

## Development Strategy

### Layer stack (build bottom-up):
```
SKILL.md          ← teaches Claude the parts/nets syntax + recipes
MCP server        ← thin: receives tool call, calls ezschem.draw(), returns SVG path
ezschem package   ← translator + netlistsvg subprocess (DONE)
```

### Circuit Recipe Library (planned for SKILL.md)
Recipes are topology templates. The AI pattern-matches from the user's description — no image recognition, just language understanding.

Each recipe contains:
- **Common names and trigger phrases** — e.g., "blinker", "flasher" → astable multivibrator
- **`parts` dict** — component types and values (user customizes values)
- **`nets` list** — connection topology

The AI's job: match user description → look up recipe → adapt values → call `ezschem.draw()`.
For circuits that don't match any recipe, the AI constructs parts/nets from first principles.

Note: recipes no longer need `hints` dicts for layout workarounds — ELK handles complex topologies automatically.

## Notes

- Project was planned in Claude.ai and built in Claude Code
- Originally used Schemdraw with custom placer/router — pivoted to netlistsvg after placer failed on cyclic topologies
- Circuit-Synth + KiCad MCP was evaluated as alternative — deferred. EZSchem is for quick standalone schematic images.
- netlistsvg's skin parser only matches by `<s:alias>` values, not `s:type` — this is why standalone NMOS/PMOS blocks don't render. Workaround: aliases on existing NPN/PNP blocks.
