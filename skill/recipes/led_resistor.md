# LED + Resistor

Simple LED with current-limiting resistor.

**Trigger phrases:** "LED circuit", "light an LED", "LED with resistor"

```python
parts = {"R1": ("res", "470"), "LED1": ("led",)}
nets = ["Vcc -> R1 -> LED1 -> GND"]
```
