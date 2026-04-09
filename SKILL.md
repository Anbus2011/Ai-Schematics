# EZSchem — Circuit Schematic Drawing Skill

You can draw circuit schematics using the `ezschem` Python package. Describe the circuit as a `parts` dict and `nets` list, then call `ezschem.draw()`.

## API

```python
import ezschem
ezschem.draw(parts, nets, output="circuit.svg")
```

**`parts`** — dict mapping ref designators to `(type,)` or `(type, value)` tuples:
```python
parts = {
    "R1": ("res", "1k"),
    "Q1": ("npn",),
    "LED1": ("led",),
}
```

**`nets`** — list of connection strings using `->` chains:
```python
nets = [
    "Vcc -> R1 -> Q1.C",
    "Q1.E -> GND",
]
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

### LED + Resistor
```python
parts = {"R1": ("res", "470"), "LED1": ("led",)}
nets = ["Vcc -> R1 -> LED1 -> GND"]
```

### Voltage Divider
```python
parts = {"R1": ("res", "10k"), "R2": ("res", "22k")}
nets = ["Vin -> R1 -> R2 -> GND", "R1 -> Vout"]
```

### Common-Emitter Amplifier
```python
parts = {
    "Q1": ("npn",),
    "Rc": ("res", "4.7k"),   # collector load
    "Re": ("res", "1k"),     # emitter degeneration
    "Rb1": ("res", "47k"),   # base bias upper
    "Rb2": ("res", "10k"),   # base bias lower
    "Cin": ("cap", "10uF"),  # input coupling
    "Cout": ("cap", "10uF"), # output coupling
}
nets = [
    "Vcc -> Rc -> Q1.C",
    "Q1.E -> Re -> GND",
    "Vcc -> Rb1 -> Q1.B",
    "Q1.B -> Rb2 -> GND",
    "Vin -> Cin -> Q1.B",
    "Q1.C -> Cout -> Vout",
]
```

### Astable Multivibrator (2-LED Flasher)
Cross-coupled NPN oscillator. C1/C2 set the flash rate.
```python
parts = {
    "Q1": ("npn",), "Q2": ("npn",),
    "R1": ("res", "470"), "R2": ("res", "470"),       # LED current limit
    "R3": ("res", "47k"), "R4": ("res", "47k"),       # base bias
    "C1": ("cap", "10uF"), "C2": ("cap", "10uF"),     # timing caps
    "LED1": ("led",), "LED2": ("led",),
}
nets = [
    "Vcc -> R1 -> LED1 -> Q1.C",    # LED1 in Q1 collector
    "Vcc -> R2 -> LED2 -> Q2.C",    # LED2 in Q2 collector
    "Q1.E -> GND",                   # emitters to ground
    "Q2.E -> GND",
    "Q1.C -> C1 -> Q2.B",           # cross-coupling
    "Q2.C -> C2 -> Q1.B",
    "Vcc -> R3 -> Q1.B",            # base bias
    "Vcc -> R4 -> Q2.B",
]
```

### H-Bridge (DC Motor Driver)
```python
parts = {
    "Q1": ("nmos",), "Q2": ("nmos",),  # high-side (simplified)
    "Q3": ("nmos",), "Q4": ("nmos",),  # low-side
}
nets = [
    "Vcc -> Q1.D", "Vcc -> Q2.D",
    "Q1.S -> Q3.D", "Q2.S -> Q4.D",
    "Q3.S -> GND", "Q4.S -> GND",
    "Q1.S -> MOTOR_A", "Q2.S -> MOTOR_B",
    "IN_A -> Q1.G", "IN_A -> Q4.G",
    "IN_B -> Q2.G", "IN_B -> Q3.G",
]
```

### Inverting Op-Amp
```python
parts = {
    "U1": ("opamp",),
    "Rf": ("res", "100k"),  # feedback
    "Rin": ("res", "10k"),  # input
}
nets = [
    "Vin -> Rin -> U1.in2",
    "U1.in2 -> Rf -> U1.out",
    "U1.in1 -> GND",
    "U1.out -> Vout",
]
```

### RC Low-Pass Filter
```python
parts = {"R1": ("res", "10k"), "C1": ("cap", "100nF")}
nets = ["Vin -> R1 -> C1 -> GND", "R1 -> Vout"]
```

### Safe Torque Off (STO) — Redundant MOSFET Switch
```python
parts = {
    "Q1": ("nmos",), "Q2": ("nmos",),
    "R1": ("res", "10k"), "R2": ("res", "10k"),
}
nets = [
    "Vcc -> Q1.D",
    "Q1.S -> Q2.D",
    "Q2.S -> MOTOR_OUT",
    "STO_A -> R1 -> GND", "STO_A -> Q1.G",
    "STO_B -> R2 -> GND", "STO_B -> Q2.G",
]
```

## Tips

- Keep schematics under ~30 components for clean layout
- Power flows top-to-bottom (Vcc at top, GND at bottom)
- Use descriptive ref designators: `Rc` for collector resistor, `Rb1`/`Rb2` for bias network
- For circuits not matching a recipe, build parts/nets from first principles — ELK handles complex topologies including cycles
