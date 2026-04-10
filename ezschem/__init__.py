"""EZSchem — AI-friendly circuit schematic generator.

Translates simple parts/nets descriptions into SVG schematics using
netlistsvg (ELK layout engine) for placement and routing.
"""

from .translator import to_yosys_json, render_svg


def draw(parts: dict, nets: list[str], hints: dict | None = None,
         output: str = "circuit.svg") -> str:
    """Generate a circuit schematic from a netlist description.

    Args:
        parts: Component definitions. Key is ref designator, value is tuple of
               (type,) or (type, value).
               Example: {"R1": ("res", "470"), "LED1": ("led",)}
        nets: Connection strings describing signal paths.
               Example: ["Vcc -> R1 -> LED1 -> GND"]
        hints: Optional layout hints per component. Supported keys:
               - "partition": int — ELK partition ID (groups components
                 into columns; same partition = same column)
               Example: {"Q1": {"partition": 0}, "Q2": {"partition": 1}}
        output: Output SVG filename.

    Returns:
        Path to the generated SVG file.

    Raises:
        ValueError: On invalid parts or nets.
        RuntimeError: If Node.js is not available.
    """
    yosys = to_yosys_json(parts, nets, hints=hints)
    return render_svg(yosys, output)
