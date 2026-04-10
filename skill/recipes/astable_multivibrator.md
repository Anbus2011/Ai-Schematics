# Astable Multivibrator (2-LED Flasher)

Cross-coupled NPN oscillator. C1/C2 set the flash rate. LEDs alternate.

**Trigger phrases:** "astable multivibrator", "LED flasher", "LED blinker", "alternating LEDs", "blinking circuit"

## Basic (auto-layout)

```python
parts = {
    "Q1": ("npn",), "Q2": ("npn",),
    "R1": ("res", "470"), "R4": ("res", "470"),       # LED current limit (outer)
    "R2": ("res", "47k"), "R3": ("res", "47k"),       # base bias (inner)
    "C1": ("cap", "10uF"), "C2": ("cap", "10uF"),     # cross-coupling caps
    "L1": ("led",), "L2": ("led",),
}
nets = [
    # Left branch (Q1 side)
    "Vcc -> R1 -> L1 -> Q1.C",
    "Vcc -> R2 -> Q1.B",
    "Q1.E -> GND",
    # Right branch (Q2 side)
    "Vcc -> R4 -> L2 -> Q2.C",
    "Vcc -> R3 -> Q2.B",
    "Q2.E -> GND",
    # Cross-coupling (the X)
    "Q1.C -> C1 -> Q2.B",
    "Q2.C -> C2 -> Q1.B",
]
```

## Symmetric (with position hints)

For a traditional symmetric layout, use `x`/`y` hints to fix component positions. ELK routes the wires automatically. Supply symbols are auto-positioned near their connected components.

```python
hints = {
    # Row 1: resistors (outer = LED current limit, inner = base bias)
    "R1": {"x": 25, "y": 0},
    "R2": {"x": 80, "y": 0},
    "R3": {"x": 130, "y": 0},
    "R4": {"x": 185, "y": 0},
    # Row 2: LEDs (outer) + cross-coupling caps (inner)
    "L1": {"x": 20, "y": 100},
    "C2": {"x": 75, "y": 100},
    "C1": {"x": 125, "y": 100},
    "L2": {"x": 180, "y": 100},
    # Row 3: transistors (side-by-side)
    "Q1": {"x": 14, "y": 200},
    "Q2": {"x": 174, "y": 200},
}
```

**Frequency ≈ 1 / (1.4 × R2 × C1)** (symmetric timing)

**Layout note:** Use 100px vertical spacing between rows to give ELK room for wire routing. Supply symbols (Vcc/GND) are auto-positioned directly above/below the components they connect to.
