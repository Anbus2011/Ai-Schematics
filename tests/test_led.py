"""Test: Simple LED + resistor circuit."""
import sys
sys.path.insert(0, r"d:\app-projects\Ai_Schematics")

import ezschem

parts = {
    "R1": ("res", "470Ω"),
    "LED1": ("led",),
}

nets = [
    "Vcc -> R1 -> LED1 -> GND",
]

ezschem.draw(parts, nets, output=r"d:\app-projects\Ai_Schematics\output\test_led.svg")
print("Done! Output saved to output/test_led.svg")
