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

For a traditional symmetric layout, use `x`/`y` hints to fix component positions. ELK routes the wires automatically.

```python
hints = {
    # Left column: R1 -> L1 -> Q1
    "R1": {"x": 25, "y": 40},
    "L1": {"x": 20, "y": 110},
    "Q1": {"x": 14, "y": 180},
    # Left-inner: R2 (base bias), C2 (cross from Q2)
    "R2": {"x": 70, "y": 40},
    "C2": {"x": 65, "y": 110},
    # Right column: R4 -> L2 -> Q2
    "R4": {"x": 175, "y": 40},
    "L2": {"x": 170, "y": 110},
    "Q2": {"x": 164, "y": 180},
    # Right-inner: R3 (base bias), C1 (cross from Q1)
    "R3": {"x": 120, "y": 40},
    "C1": {"x": 115, "y": 110},
}
```

**Frequency ≈ 1 / (1.4 × R2 × C1)** (symmetric timing)

**Layout note:** Group left-branch nets together, then right-branch, then cross-coupling last. The `x`/`y` hints switch ELK to INTERACTIVE mode, which respects component positions while still routing wires automatically.
