# RC Low-Pass Filter

First-order passive low-pass filter.

**Trigger phrases:** "low-pass filter", "RC filter", "LP filter", "noise filter"

```python
parts = {"R1": ("res", "10k"), "C1": ("cap", "100nF")}
nets = ["Vin -> R1 -> C1 -> GND", "R1 -> Vout"]
```

**Cutoff frequency = 1 / (2π × R × C)** (≈ 159 Hz with these values)
