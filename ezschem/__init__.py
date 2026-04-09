"""EZSchem — AI-friendly circuit schematic generator.

Translates simple parts/nets descriptions into SVG schematics using
netlistsvg (ELK layout engine) for placement and routing.
"""

from pathlib import Path

from .translator import to_yosys_json, render_svg, ensure_skin


def draw(parts: dict, nets: list[str], hints: dict | None = None,
         output: str = "circuit.svg") -> str:
    """Generate a circuit schematic from a netlist description.

    Args:
        parts: Component definitions. Key is ref designator, value is tuple of
               (type,) or (type, value).
               Example: {"R1": ("res", "470"), "LED1": ("led",)}
        nets: Connection strings describing signal paths.
               Example: ["Vcc -> R1 -> LED1 -> GND"]
        hints: Reserved for future use (layout hints).
        output: Output SVG filename.

    Returns:
        Path to the generated SVG file.

    Raises:
        ValueError: On invalid parts or nets.
        RuntimeError: If netlistsvg or Node.js is not available.
    """
    skin = ensure_skin()
    yosys = to_yosys_json(parts, nets)
    return render_svg(yosys, output, skin)
