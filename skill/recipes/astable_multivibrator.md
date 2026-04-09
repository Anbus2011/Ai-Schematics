# Astable Multivibrator (2-LED Flasher)

Cross-coupled NPN oscillator. C1/C2 set the flash rate. LEDs alternate.

**Trigger phrases:** "astable multivibrator", "LED flasher", "LED blinker", "alternating LEDs", "blinking circuit"

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

**Frequency ≈ 1 / (1.4 × R3 × C1)** (symmetric timing)

**Layout note:** List Q1 branch nets before Q2 branch nets for better ELK symmetry.
