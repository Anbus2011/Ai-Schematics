# Astable Multivibrator (2-LED Flasher)

Cross-coupled NPN oscillator. C1/C2 set the flash rate. LEDs alternate.

**Trigger phrases:** "astable multivibrator", "LED flasher", "LED blinker", "alternating LEDs", "blinking circuit"

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

**Frequency ≈ 1 / (1.4 × R2 × C1)** (symmetric timing)

**Layout note:** Group left-branch nets together, then right-branch, then cross-coupling last. This helps ELK keep the two halves in adjacent columns.
