# Inverting Op-Amp

Classic inverting amplifier configuration.

**Trigger phrases:** "inverting amplifier", "inverting op-amp", "op-amp inverter"

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

**Gain = -Rf / Rin** (= -10 with these values)
