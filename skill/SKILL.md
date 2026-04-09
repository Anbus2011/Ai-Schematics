# EZSchem — Circuit Schematic Drawing Skill

Draw circuit schematics using the `draw_schematic` MCP tool or `ezschem.draw()` Python API. Describe circuits as `parts` and `nets`, EZSchem handles layout and rendering.

## Quick Start

```python
parts = {"R1": ("res", "470"), "LED1": ("led",)}
nets = ["Vcc -> R1 -> LED1 -> GND"]
```

Call `draw_schematic(parts, nets)` via MCP, or:
```python
import ezschem
ezschem.draw(parts, nets, output="circuit.svg")
```

## Component Types

| Type | Description | Pins |
|------|-------------|------|
| `res` | Resistor | `.start`/`.end` (auto-assigned in chains) |
| `cap` | Capacitor | `.start`/`.end` |
| `ind` | Inductor | `.start`/`.end` |
| `diode` | Diode | `.A` (anode) / `.K` (cathode), or `.start`/`.end` |
| `led` | LED | `.A` / `.K`, or `.start`/`.end` |
| `zener` | Zener diode | `.A` / `.K`, or `.start`/`.end` |
| `npn` | NPN BJT | `.B` (base), `.C` (collector), `.E` (emitter) |
| `pnp` | PNP BJT | `.B`, `.C`, `.E` |
| `nmos` | N-ch MOSFET | `.G` (gate), `.D` (drain), `.S` (source) |
| `pmos` | P-ch MOSFET | `.G`, `.D`, `.S` |
| `opamp` | Op-amp | `.in1` (+), `.in2` (-), `.out` |
| `sw` | Switch | `.start`/`.end` |

## Net String Rules

1. **Chain pass-through:** `"Vcc -> R1 -> LED1 -> GND"` connects Vcc→R1.start, R1.end→LED1.start, LED1.end→GND
2. **Explicit pins:** `"Q1.C"` connects only that pin — no pass-through
3. **Two-terminal auto-assign:** First use of `R1` gets `.start`, second gets `.end`
4. **Multi-terminal require explicit pins:** `Q1.B`, `Q1.C`, `Q1.E` — always specify
5. **Power/ground** (`Vcc`, `GND`, `Vdd`, `Vss`) — each occurrence draws a local symbol. Safe to use many times.
6. **Named nets** — any name not in `parts` and not power/ground becomes a labeled port (e.g., `Vin`, `Vout`, `MCU_PIN`)

## Circuit Recipes

Ready-to-use topology templates. Match the user's request to a recipe, adapt component values, then call `draw_schematic`.

- [LED + Resistor](recipes/led_resistor.md)
- [Voltage Divider](recipes/voltage_divider.md)
- [Common-Emitter Amplifier](recipes/common_emitter.md)
- [Astable Multivibrator (2-LED Flasher)](recipes/astable_multivibrator.md)
- [H-Bridge (DC Motor Driver)](recipes/h_bridge.md)
- [Inverting Op-Amp](recipes/inverting_opamp.md)
- [RC Low-Pass Filter](recipes/rc_lowpass.md)
- [Safe Torque Off (STO)](recipes/sto_circuit.md)

For circuits not matching a recipe, build `parts`/`nets` from first principles — the layout engine handles complex topologies including cycles.

## Layout Tips

The ELK layout engine is automatic but its output is influenced by **net ordering**:

- **List symmetric halves in parallel order.** For an astable, list Q1 branch nets first, then Q2 — don't interleave.
- **Put the main signal path first.** Power→load→ground chain comes before bias/feedback nets.
- **Group related nets together.** All connections to one component should be adjacent.
- **Keep schematics under ~30 components** for clean layout.
- Power flows top-to-bottom (Vcc at top, GND at bottom).
- Use descriptive ref designators: `Rc` for collector resistor, `Rb1`/`Rb2` for bias network.
