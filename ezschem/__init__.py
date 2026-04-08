"""EZSchem — AI-friendly circuit schematic generator wrapping Schemdraw."""

from .parser import parse
from .placer import place
from .renderer import render


def draw(parts: dict, nets: list[str], hints: dict | None = None,
         output: str = "circuit.png", dpi: int = 150):
    """Generate a circuit schematic from a netlist description.

    Args:
        parts: Component definitions. Key is ref designator, value is tuple of
               (type,) or (type, value).
               Example: {"R1": ("res", "470"), "LED1": ("led",)}
        nets: Connection strings describing signal paths.
               Example: ["Vcc -> R1 -> LED1 -> GND"]
        hints: Optional layout hints (not yet implemented).
        output: Output filename (.png or .svg)
        dpi: Resolution for PNG output

    Returns:
        The Schemdraw Drawing object.
    """
    # Parse netlist into circuit graph
    graph = parse(parts, nets)

    # Place components on grid
    placements = place(graph)

    # TODO: Apply layout hints

    # Render to image
    drawing = render(graph, placements, output=output, dpi=dpi)

    return drawing
