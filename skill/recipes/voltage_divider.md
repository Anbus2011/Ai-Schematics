# Voltage Divider

Resistive voltage divider with output tap.

**Trigger phrases:** "voltage divider", "resistor divider", "divide voltage"

```python
parts = {"R1": ("res", "10k"), "R2": ("res", "22k")}
nets = ["Vin -> R1 -> R2 -> GND", "R1 -> Vout"]
```

**Vout = Vin × R2 / (R1 + R2)**
