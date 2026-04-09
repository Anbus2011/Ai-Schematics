"""EZSchem MCP Server — exposes draw_schematic tool for Claude."""

import sys
from pathlib import Path

# Ensure the ezschem package is importable
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("EZSchem")


@mcp.tool()
def draw_schematic(parts: dict, nets: list[str], output: str = "circuit.svg") -> str:
    """Generate a circuit schematic SVG from a netlist description.

    Args:
        parts: Component definitions. Keys are ref designators, values are
               [type] or [type, value] lists.
               Example: {"R1": ["res", "470"], "Q1": ["npn"], "LED1": ["led"]}
        nets: Connection strings describing signal paths.
              Example: ["Vcc -> R1 -> LED1 -> GND", "Q1.B -> R2 -> Vcc"]
        output: Output SVG filename (default: circuit.svg).

    Component types: res, cap, ind, diode, led, zener, npn, pnp, nmos, pmos, opamp, sw

    Pin aliases:
      Two-terminal (res, cap, ind, sw): .start, .end (auto-assigned in chains)
      Diode/LED: .A (anode), .K (cathode)
      BJT: .B (base), .C (collector), .E (emitter)
      MOSFET: .G (gate), .D (drain), .S (source)
      Op-amp: .in1 (+), .in2 (-), .out

    Special net names: Vcc, VCC, Vdd, VDD, V+ (power symbols)
                       GND, Vss, VSS, V- (ground symbols)
    Each occurrence spawns a local symbol — no global short-circuit.

    Returns:
        Absolute path to the generated SVG file.
    """
    import ezschem

    # MCP/JSON sends lists, but ezschem expects tuples for part specs
    normalized_parts = {}
    for name, spec in parts.items():
        if isinstance(spec, list):
            normalized_parts[name] = tuple(spec)
        else:
            normalized_parts[name] = spec

    result = ezschem.draw(normalized_parts, nets, output=output)
    return str(Path(result).resolve())


if __name__ == "__main__":
    mcp.run(transport="stdio")
