# EZSchem

AI-friendly circuit schematic generator. Describe circuits with simple `parts`/`nets` dicts, get clean SVG schematics.

```python
import ezschem

parts = {"R1": ("res", "470"), "LED1": ("led",)}
nets = ["Vcc -> R1 -> LED1 -> GND"]
ezschem.draw(parts, nets, output="circuit.svg")
```

## How It Works

```
parts/nets (Python) → Yosys JSON → netlistsvg (ELK layout engine) → SVG
```

The AI describes circuit topology. EZSchem translates to a format the [netlistsvg](https://github.com/nturley/netlistsvg) tool understands, which uses the Eclipse Layout Kernel for automatic placement and routing.

## Installation

### Prerequisites

- **Python 3.10+**
- **Node.js** (LTS) — for the netlistsvg layout engine

```bash
# Windows
winget install OpenJS.NodeJS.LTS

# macOS
brew install node

# Linux
sudo apt install nodejs npm
```

### Install EZSchem

```bash
git clone https://github.com/Anbus2011/Ai-Schematics.git
cd Ai-Schematics
npm install        # installs elkjs, lodash, and other JS dependencies
pip install mcp    # for MCP server support (optional)
```

## Usage

### Python API

```python
import ezschem

parts = {
    "Q1": ("npn",),
    "Rc": ("res", "4.7k"),
    "Re": ("res", "1k"),
}
nets = [
    "Vcc -> Rc -> Q1.C",
    "Q1.E -> Re -> GND",
    "Vin -> Q1.B",
]
ezschem.draw(parts, nets, output="amplifier.svg")
```

### MCP Server (Claude Desktop / Claude Code)

The MCP server exposes a `draw_schematic` tool that Claude can call directly.

#### Claude Code

The `.mcp.json` in the project root auto-configures the server. Restart Claude Code after cloning.

To configure manually:
```bash
claude mcp add ezschem -- python /path/to/Ai-Schematics/mcp_server.py
```

#### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ezschem": {
      "command": "python",
      "args": ["/path/to/Ai-Schematics/mcp_server.py"],
      "env": {
        "EZSCHEM_OUTPUT_DIR": "/path/to/your/output/folder"
      }
    }
  }
}
```

Set `EZSCHEM_OUTPUT_DIR` to where you want SVG files saved. If not set, defaults to `~/ezschem_output/`.

### Skill File

The [skill/SKILL.md](skill/SKILL.md) teaches Claude the `parts`/`nets` syntax and includes circuit recipes for common topologies. Point Claude at this file for best results.

## Component Types

| Type | Description | Pins |
|------|-------------|------|
| `res` | Resistor | `.start`/`.end` (auto-assigned) |
| `cap` | Capacitor | `.start`/`.end` |
| `ind` | Inductor | `.start`/`.end` |
| `diode` | Diode | `.A`/`.K` or `.start`/`.end` |
| `led` | LED | `.A`/`.K` or `.start`/`.end` |
| `zener` | Zener diode | `.A`/`.K` or `.start`/`.end` |
| `npn` | NPN BJT | `.B`, `.C`, `.E` |
| `pnp` | PNP BJT | `.B`, `.C`, `.E` |
| `nmos` | N-ch MOSFET | `.G`, `.D`, `.S` |
| `pmos` | P-ch MOSFET | `.G`, `.D`, `.S` |
| `opamp` | Op-amp | `.in1`, `.in2`, `.out` |
| `sw` | Switch | `.start`/`.end` |

## Net Syntax

```python
nets = [
    "Vcc -> R1 -> LED1 -> GND",   # chain: R1.start→R1.end pass-through
    "Q1.C -> R2 -> Vcc",          # explicit pin on Q1
    "Vin -> C1 -> Q1.B",          # named net (Vin) becomes a port label
]
```

- **Power/ground** (`Vcc`, `GND`, `Vdd`, `Vss`) — each use draws a local symbol
- **Named nets** — any unrecognized name becomes a labeled port

## Circuit Recipes

See [skill/recipes/](skill/recipes/) for ready-to-use templates:

- [LED + Resistor](skill/recipes/led_resistor.md)
- [Voltage Divider](skill/recipes/voltage_divider.md)
- [Common-Emitter Amplifier](skill/recipes/common_emitter.md)
- [Astable Multivibrator](skill/recipes/astable_multivibrator.md)
- [H-Bridge](skill/recipes/h_bridge.md)
- [Inverting Op-Amp](skill/recipes/inverting_opamp.md)
- [RC Low-Pass Filter](skill/recipes/rc_lowpass.md)
- [Safe Torque Off (STO)](skill/recipes/sto_circuit.md)

## Known Limitations

- **NMOS/PMOS symbols** render as NPN/PNP (netlistsvg skin limitation) — topology is correct
- **Layout symmetry** — ELK's auto-layout doesn't optimize for visual symmetry; net ordering in recipes is the primary influence
- **SVG only** — no PNG output (use a converter like cairosvg if needed)
- **~30 component limit** — larger circuits may have cluttered layout
