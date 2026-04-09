# Safe Torque Off (STO) — Redundant MOSFET Switch

Two N-channel MOSFETs in series with independent enable signals and pull-down resistors. Both channels must be enabled for current to flow.

**Trigger phrases:** "safe torque off", "STO", "redundant switch", "safety interlock"

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

**Safety principle:** Independent enable signals (STO_A, STO_B) from separate safety controllers. Pull-down resistors ensure gates default to OFF.
