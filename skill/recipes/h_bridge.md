# H-Bridge (DC Motor Driver)

Four N-channel MOSFETs in H configuration for bidirectional motor control.

**Trigger phrases:** "H-bridge", "motor driver", "bidirectional motor", "full bridge"

```python
parts = {
    "Q1": ("nmos",), "Q2": ("nmos",),  # high-side
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

**Note:** Simplified — real H-bridges need gate drivers for high-side N-ch MOSFETs or use P-ch on the high side.
