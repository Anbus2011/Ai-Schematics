# Common-Emitter Amplifier

Single-stage NPN amplifier with bias network and coupling capacitors.

**Trigger phrases:** "common emitter", "CE amplifier", "transistor amplifier", "NPN amplifier"

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

**Gain ≈ -Rc / Re** (with emitter degeneration)
