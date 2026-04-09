"""EZSchem MCP Server — exposes draw_schematic tool for Claude."""

import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure the ezschem package is importable
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("EZSchem")


def _output_dir() -> Path:
    """Resolve the output directory from env or default."""
    env_dir = os.environ.get("EZSCHEM_OUTPUT_DIR")
    if env_dir:
        d = Path(env_dir)
    else:
        d = Path.home() / "ezschem_output"
    d.mkdir(parents=True, exist_ok=True)
    return d


@mcp.tool()
def draw_schematic(parts: dict, nets: list[str], name: str = "") -> str:
    """Generate a circuit schematic SVG from a netlist description.

    Args:
        parts: Component definitions. Keys are ref designators, values are
               [type] or [type, value] lists.
               Example: {"R1": ["res", "470"], "Q1": ["npn"], "LED1": ["led"]}
        nets: Connection strings describing signal paths.
              Example: ["Vcc -> R1 -> LED1 -> GND", "Q1.B -> R2 -> Vcc"]
        name: Optional circuit name for the output filename.
              If empty, uses a timestamp.

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
    for ref, spec in parts.items():
        normalized_parts[ref] = tuple(spec) if isinstance(spec, list) else spec

    # Build output path
    if name:
        filename = name.replace(" ", "_") + ".svg"
    else:
        filename = datetime.now().strftime("schematic_%Y%m%d_%H%M%S.svg")

    output_path = _output_dir() / filename

    ezschem.draw(normalized_parts, nets, output=str(output_path))
    return str(output_path.resolve())


if __name__ == "__main__":
    mcp.run(transport="stdio")
