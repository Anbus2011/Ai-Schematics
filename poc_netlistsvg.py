"""Proof-of-Concept: netlistsvg as layout/rendering engine for EZSchem.

This standalone script evaluates replacing the custom placer/router/renderer
pipeline with netlistsvg (which uses the Eclipse Layout Kernel under the hood).

Does NOT modify the existing ezschem/ package.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants: type and pin mapping from ezschem → netlistsvg skin types
# ---------------------------------------------------------------------------

EZSCHEM_TO_SKIN_TYPE = {
    "res": "r_v",
    "cap": "c_v",
    "ind": "l_v",
    "diode": "diode_v",
    "led": "diode_v",
    "zener": "diode_v",
    "npn": "q_npn",
    "pnp": "q_pnp",
    "nmos": "nmos",       # custom skin symbol (copied from q_npn)
    "pmos": "pmos",       # custom skin symbol (copied from q_pnp)
    "opamp": "opamp",
    "sw": "r_v",          # no switch in analog skin; resistor stand-in
}

# Maps ezschem resolved pin names → netlistsvg skin port IDs.
# The nmos/pmos skin symbols reuse NPN/PNP port positions (C/B/E) so
# the translator maps drain→C, gate→B, source→E.
EZSCHEM_PIN_TO_SKIN_PORT = {
    # Two-terminal passives
    "start": "A",
    "end": "B",
    # BJTs — direct match
    "collector": "C",
    "base": "B",
    "emitter": "E",
    # FETs — mapped onto the BJT port layout of the custom skin symbol
    "drain": "C",
    "gate": "B",
    "source": "E",
    # Op-amp
    "in1": "+",
    "in2": "-",
    "out": "OUT",
}

# Component types whose natural orientation is vertical (power→ground).
# We inject ELK direction hints for these.
VERTICAL_TYPES = {"r_v", "c_v", "l_v", "diode_v", "vcc", "gnd"}

# Power/ground net names
POWER_NETS = {"Vcc", "Vdd", "V+", "VCC", "VDD"}
GROUND_NETS = {"GND", "Vss", "VSS", "V-"}

# Anchor aliases (mirrors ezschem/components.py for standalone use)
_TWO_TERMINAL = {"p": "start", "n": "end", "start": "start", "end": "end",
                 "A": "start", "K": "end", "anode": "start", "cathode": "end"}
_BJT = {"B": "base", "C": "collector", "E": "emitter",
        "base": "base", "collector": "collector", "emitter": "emitter"}
_FET = {"G": "gate", "D": "drain", "S": "source",
        "gate": "gate", "drain": "drain", "source": "source"}

ANCHOR_ALIASES = {
    "res": _TWO_TERMINAL, "cap": _TWO_TERMINAL, "ind": _TWO_TERMINAL,
    "sw": _TWO_TERMINAL, "diode": _TWO_TERMINAL, "led": _TWO_TERMINAL,
    "zener": _TWO_TERMINAL,
    "npn": _BJT, "pnp": _BJT,
    "nmos": _FET, "pmos": _FET,
}

DEFAULT_PINS = {
    "res": ("start", "end"), "cap": ("start", "end"), "ind": ("start", "end"),
    "sw": ("start", "end"), "diode": ("start", "end"), "led": ("start", "end"),
    "zener": ("start", "end"),
}


# ---------------------------------------------------------------------------
# 1. Custom Skin Generator
# ---------------------------------------------------------------------------

ANALOG_SVG_URL = (
    "https://raw.githubusercontent.com/nturley/netlistsvg/master/lib/analog.svg"
)

# NMOS symbol: copied from q_npn with visual modifications:
#   - Gap between gate plate and channel (insulated gate)
#   - Arrow on source pointing inward (N-channel convention)
#   - Same port positions (C=drain@top, B=gate@left, E=source@bottom)
NMOS_SVG_BLOCK = '''
<g s:type="nmos" s:width="32" s:height="32" transform="translate(15,420)">
  <text x="35" y="20" s:attribute="ref" class="$cell_id">M1</text>
  <circle r="16" cx="16" cy="16" class="symbol $cell_id"/>
  <path d="M0,16 H10" class="detail $cell_id"/>
  <path d="M11,6 V26" class="detail $cell_id"/>
  <path d="M14,6 V12 M14,14 V18 M14,20 V26" class="detail $cell_id"/>
  <path d="M14,9 H23 V2" class="detail $cell_id"/>
  <path d="M14,23 H23 V29" class="detail $cell_id"/>
  <path d="M14,18 20,16 14,14 z" style="fill:#000000" class="$cell_id"/>
  <g s:x="23" s:y="2" s:pid="C" s:position="top"/>
  <g s:x="0" s:y="16" s:pid="B" s:position="left"/>
  <g s:x="23" s:y="29" s:pid="E" s:position="bottom"/>
</g>
'''

PMOS_SVG_BLOCK = '''
<g s:type="pmos" s:width="32" s:height="32" transform="translate(15,460)">
  <text x="35" y="20" s:attribute="ref" class="$cell_id">M2</text>
  <circle r="16" cx="16" cy="16" class="symbol $cell_id"/>
  <path d="M0,16 H10" class="detail $cell_id"/>
  <path d="M11,6 V26" class="detail $cell_id"/>
  <path d="M14,6 V12 M14,14 V18 M14,20 V26" class="detail $cell_id"/>
  <path d="M14,9 H23 V2" class="detail $cell_id"/>
  <path d="M14,23 H23 V29" class="detail $cell_id"/>
  <path d="M20,18 14,16 20,14 z" style="fill:#000000" class="$cell_id"/>
  <g s:x="23" s:y="2" s:pid="C" s:position="top"/>
  <g s:x="0" s:y="16" s:pid="B" s:position="left"/>
  <g s:x="23" s:y="29" s:pid="E" s:position="bottom"/>
</g>
'''


def download_and_patch_skin(output_path: str = "custom_analog.svg") -> str:
    """Download the default analog.svg and inject NMOS/PMOS symbols."""
    cache = Path(output_path)
    if cache.exists():
        print(f"  Skin already exists: {cache}")
        return str(cache)

    print(f"  Downloading analog.svg from GitHub...")
    try:
        req = urllib.request.Request(ANALOG_SVG_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            svg_text = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  ERROR: Failed to download skin: {e}")
        print(f"  Manually download from: {ANALOG_SVG_URL}")
        sys.exit(1)

    # Strategy: Add aliases to existing transistor blocks AND inject new NMOS/PMOS
    # blocks. The alias approach ensures matching works even if standalone blocks fail.

    # Add nmos/pmos aliases to existing NPN/PNP blocks
    svg_text = svg_text.replace(
        '<s:alias val="q_npn"/>',
        '<s:alias val="q_npn"/>\n  <s:alias val="nmos"/>',
    )
    svg_text = svg_text.replace(
        '<s:alias val="q_pnp"/>',
        '<s:alias val="q_pnp"/>\n  <s:alias val="pmos"/>',
    )

    # Also inject standalone NMOS/PMOS blocks with distinct visuals
    closing_tag = "</svg>"
    if closing_tag not in svg_text:
        print("  ERROR: Could not find </svg> tag in downloaded skin")
        sys.exit(1)

    patched = svg_text.replace(closing_tag, NMOS_SVG_BLOCK + PMOS_SVG_BLOCK + closing_tag)
    cache.write_text(patched, encoding="utf-8")
    print(f"  Saved custom skin with NMOS/PMOS: {cache}")
    return str(cache)


# ---------------------------------------------------------------------------
# 2. Netlist Translator: parts/nets → Yosys JSON
# ---------------------------------------------------------------------------

class NetIdAllocator:
    """Assigns unique integer IDs to net nodes using union-find."""

    def __init__(self):
        self._next_id = 2  # start at 2; 0/1 reserved as convention
        self._pin_to_net: dict[str, int] = {}  # "R1.start" → net_id
        self._named_nets: dict[str, int] = {}  # "STO_A" → net_id

    def get_or_create(self, key: str) -> int:
        """Get/create a net ID for a pin key like 'R1.start' or net name like 'STO_A'."""
        if key not in self._pin_to_net:
            self._pin_to_net[key] = self._next_id
            self._next_id += 1
        return self._pin_to_net[key]

    def unify(self, key_a: str, key_b: str) -> int:
        """Ensure two keys share the same net ID. Returns the shared ID."""
        id_a = self._pin_to_net.get(key_a)
        id_b = self._pin_to_net.get(key_b)

        if id_a is not None and id_b is not None:
            # Both exist — merge: rewrite all occurrences of id_b to id_a
            if id_a != id_b:
                for k, v in self._pin_to_net.items():
                    if v == id_b:
                        self._pin_to_net[k] = id_a
            return id_a
        elif id_a is not None:
            self._pin_to_net[key_b] = id_a
            return id_a
        elif id_b is not None:
            self._pin_to_net[key_a] = id_b
            return id_b
        else:
            new_id = self._next_id
            self._next_id += 1
            self._pin_to_net[key_a] = new_id
            self._pin_to_net[key_b] = new_id
            return new_id

    def dump(self) -> dict[str, int]:
        """Return the full pin→net_id mapping for debugging."""
        return dict(self._pin_to_net)


def _resolve_alias(comp_type: str, alias: str) -> str:
    """Resolve a pin alias to the canonical ezschem pin name."""
    aliases = ANCHOR_ALIASES.get(comp_type, {})
    resolved = aliases.get(alias)
    if resolved is None:
        raise ValueError(f"Invalid pin '{alias}' for component type '{comp_type}'")
    return resolved


def _parse_token(token: str, parts: dict) -> tuple[str, str | None]:
    """Parse 'Q1.D' → ('Q1', 'drain') or 'Vcc' → ('Vcc', None)."""
    if "." in token:
        comp_name, pin_alias = token.split(".", 1)
        if comp_name not in parts:
            raise ValueError(f"Component '{comp_name}' not in parts dict")
        comp_type = parts[comp_name][0]
        resolved_pin = _resolve_alias(comp_type, pin_alias)
        return comp_name, resolved_pin
    return token, None


def _auto_assign_pin(comp_name: str, parts: dict, use_counts: dict) -> str:
    """Auto-assign start/end for two-terminal components."""
    comp_type = parts[comp_name][0]
    defaults = DEFAULT_PINS.get(comp_type)
    if defaults is None:
        raise ValueError(
            f"Component '{comp_name}' ({comp_type}) requires explicit pin "
            f"(e.g., '{comp_name}.B')"
        )
    idx = min(use_counts.get(comp_name, 0), len(defaults) - 1)
    use_counts[comp_name] = use_counts.get(comp_name, 0) + 1
    return defaults[idx]


def _pin_key(comp_or_net: str, pin: str | None) -> str:
    """Create a canonical key for net-ID lookup."""
    if pin:
        return f"{comp_or_net}.{pin}"
    return comp_or_net  # named net node


def circuit_graph_to_yosys_json(
    parts: dict,
    nets: list[str],
    module_name: str = "circuit",
) -> dict:
    """Translate ezschem parts/nets into a Yosys-format JSON netlist.

    Args:
        parts: {"R1": ("res", "10k"), "Q1": ("nmos",), ...}
        nets: ["Vcc -> R1 -> Q1.D", "Q1.S -> GND", ...]
        module_name: Name for the top-level module.

    Returns:
        dict suitable for json.dumps() → netlistsvg input.
    """
    allocator = NetIdAllocator()
    use_counts: dict[str, int] = {}  # for auto-assigning two-terminal pins

    # Supply nets (Vcc, GND) are LOCAL symbols — each occurrence in a net chain
    # spawns a separate cell connected to the adjacent component's net, NOT a
    # single shared node. We collect (supply_name, net_id) pairs during parsing.
    supply_instances: list[tuple[str, int]] = []

    # Non-supply named nets (STO_A, MOTOR_OUT) ARE shared across chains.
    signal_net_nodes: set[str] = set()

    # --- Pass 1: Walk all net chains, assign/unify net IDs ---
    #
    # Chain semantics: "A -> R1 -> B" means A connects to R1.start,
    # R1.end connects to B. A two-terminal component in the middle of a
    # chain is a pass-through (entry pin → exit pin). Components with
    # explicit pins (e.g. "Q1.D") connect only that pin.
    for net_str in nets:
        tokens = [t.strip() for t in net_str.split("->")]
        if len(tokens) < 2:
            raise ValueError(f"Net must have >= 2 nodes: '{net_str}'")

        prev_key: str | None = None

        for token in tokens:
            comp_name, pin = _parse_token(token, parts)
            is_supply = comp_name in POWER_NETS or comp_name in GROUND_NETS

            if is_supply:
                if prev_key is not None:
                    net_id = allocator.get_or_create(prev_key)
                    supply_instances.append((comp_name, net_id))
                    prev_key = None
                    continue
                else:
                    fresh_key = f"__supply_{len(supply_instances)}__"
                    allocator.get_or_create(fresh_key)
                    supply_instances.append((comp_name, allocator.get_or_create(fresh_key)))
                    prev_key = fresh_key
                    continue

            if comp_name in parts:
                if pin is not None:
                    # Explicit pin — single connection point
                    key = _pin_key(comp_name, pin)
                    allocator.get_or_create(key)
                    if prev_key is not None:
                        allocator.unify(prev_key, key)
                    prev_key = key
                else:
                    # Implicit two-terminal pass-through:
                    # prev connects to start, end becomes the new prev
                    defaults = DEFAULT_PINS.get(parts[comp_name][0])
                    if defaults is None:
                        raise ValueError(
                            f"Component '{comp_name}' ({parts[comp_name][0]}) "
                            f"requires explicit pin"
                        )
                    entry_key = _pin_key(comp_name, defaults[0])  # start
                    exit_key = _pin_key(comp_name, defaults[1])   # end
                    allocator.get_or_create(entry_key)
                    allocator.get_or_create(exit_key)
                    if prev_key is not None:
                        allocator.unify(prev_key, entry_key)
                    prev_key = exit_key
            else:
                # Signal net node (STO_A, MOTOR_OUT, etc.)
                key = _pin_key(comp_name, None)
                signal_net_nodes.add(comp_name)
                allocator.get_or_create(key)
                if prev_key is not None:
                    allocator.unify(prev_key, key)
                prev_key = key

    # --- Pass 2: Build cells dict ---
    cells = {}
    net_map = allocator.dump()

    for comp_name, spec in parts.items():
        comp_type = spec[0]
        value = spec[1] if len(spec) > 1 else None
        skin_type = EZSCHEM_TO_SKIN_TYPE.get(comp_type, "generic")

        connections = {}
        port_directions = {}
        for full_key, net_id in net_map.items():
            if "." in full_key:
                key_comp, key_pin = full_key.split(".", 1)
                if key_comp == comp_name:
                    port_id = EZSCHEM_PIN_TO_SKIN_PORT.get(key_pin, key_pin)
                    connections[port_id] = [net_id]
                    if key_pin in ("start", "collector", "drain", "in1", "in2"):
                        port_directions[port_id] = "input"
                    else:
                        port_directions[port_id] = "output"

        attributes = {"ref": comp_name}
        if value:
            attributes["value"] = value
        if skin_type in VERTICAL_TYPES:
            attributes["elk.direction"] = "DOWN"

        cells[comp_name] = {
            "type": skin_type,
            "port_directions": port_directions,
            "connections": connections,
            "attributes": attributes,
        }

    # --- Pass 3: Local supply symbol cells ---
    supply_counter = defaultdict(int)
    for supply_name, net_id in supply_instances:
        # Resolve net_id through the allocator (union-find may have merged)
        # Find the canonical ID by looking up any key that maps to this ID
        resolved_id = net_id
        for k, v in net_map.items():
            if v != net_id:
                continue
            # This key was part of the same original group; take the mapped value
            resolved_id = v
            break

        supply_counter[supply_name] += 1
        cell_name = f"{supply_name}_{supply_counter[supply_name]}"
        is_power = supply_name in POWER_NETS
        skin_type = "vcc" if is_power else "gnd"
        cells[cell_name] = {
            "type": skin_type,
            "port_directions": {"A": "output" if is_power else "input"},
            "connections": {"A": [resolved_id]},
            "attributes": {
                "ref": supply_name,
                "elk.direction": "DOWN",
            },
        }

    # --- Pass 4: Module ports for signal net nodes ---
    ports = {}
    for net_name in signal_net_nodes:
        net_id = net_map.get(net_name)
        if net_id is not None:
            direction = "output" if "OUT" in net_name.upper() else "input"
            ports[net_name] = {
                "direction": direction,
                "bits": [net_id],
            }

    return {
        "modules": {
            module_name: {
                "ports": ports,
                "cells": cells,
            }
        }
    }


# ---------------------------------------------------------------------------
# 3. Node.js / netlistsvg execution
# ---------------------------------------------------------------------------

def check_node_installed() -> bool:
    """Check if Node.js and npx are available."""
    node = shutil.which("node")
    if not node:
        print("\n  Node.js is NOT installed.")
        print("  Install via: winget install OpenJS.NodeJS.LTS")
        print("  Or download: https://nodejs.org/")
        return False
    print(f"  Node.js found: {node}")
    npx = shutil.which("npx")
    if not npx:
        print("  WARNING: npx not found (included with Node.js >= 8)")
        return False
    print(f"  npx found: {npx}")
    return True


def run_netlistsvg(json_path: str, svg_path: str, skin_path: str) -> bool:
    """Execute netlistsvg via npx."""
    npx = shutil.which("npx")
    if not npx:
        print("  ERROR: npx not found on PATH")
        return False
    cmd = [npx, "netlistsvg", json_path, "-o", svg_path, "--skin", skin_path]
    print(f"\n  Running: npx netlistsvg {json_path} -o {svg_path} --skin {skin_path}")
    try:
        env = dict(os.environ)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, env=env,
        )
        if result.returncode != 0:
            print(f"  STDERR: {result.stderr.strip()}")
            return False
        if result.stdout.strip():
            print(f"  STDOUT: {result.stdout.strip()}")
        print(f"  SVG written to: {svg_path}")
        return True
    except FileNotFoundError:
        print("  ERROR: npx command not found")
        return False
    except subprocess.TimeoutExpired:
        print("  ERROR: netlistsvg timed out (120s)")
        return False


# ---------------------------------------------------------------------------
# 4. Verification: pretty-print the generated JSON
# ---------------------------------------------------------------------------

def verify_net_ids(yosys_json: dict) -> None:
    """Print a summary of net ID assignments for manual verification."""
    module = next(iter(yosys_json["modules"].values()))
    cells = module["cells"]
    ports = module.get("ports", {})

    # Invert: net_id → list of (cell_name, port_name)
    net_to_pins: dict[int, list[str]] = defaultdict(list)

    for cell_name, cell in cells.items():
        for port_name, bits in cell["connections"].items():
            for bit_id in bits:
                net_to_pins[bit_id].append(f"{cell_name}.{port_name}")

    for port_name, port_info in ports.items():
        for bit_id in port_info["bits"]:
            net_to_pins[bit_id].append(f"[PORT:{port_name}]")

    print("\n  === Net ID Verification ===")
    for net_id in sorted(net_to_pins.keys()):
        pins = net_to_pins[net_id]
        print(f"    Net {net_id:3d}: {', '.join(pins)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  netlistsvg PoC — EZSchem Architecture Pivot Evaluation")
    print("=" * 60)

    # --- Step 1: Generate custom skin ---
    print("\n[1/4] Generating custom analog skin with NMOS/PMOS...")
    skin_path = download_and_patch_skin("custom_analog.svg")

    # --- Step 2: Define the STO circuit ---
    print("\n[2/4] Building STO circuit netlist...")
    parts = {
        "Q1": ("nmos",),
        "Q2": ("nmos",),
        "R1": ("res", "10k"),
        "R2": ("res", "10k"),
    }
    nets = [
        "Vcc -> Q1.D",
        "Q1.S -> Q2.D",
        "Q2.S -> MOTOR_OUT",
        "STO_A -> R1 -> GND",
        "STO_B -> R2 -> GND",
        "STO_A -> Q1.G",
        "STO_B -> Q2.G",
    ]

    print(f"  Parts: {parts}")
    print(f"  Nets:")
    for n in nets:
        print(f"    {n}")

    # --- Step 3: Translate to Yosys JSON ---
    print("\n[3/4] Translating to Yosys JSON...")
    yosys_json = circuit_graph_to_yosys_json(parts, nets, module_name="STO_Circuit")

    json_path = "test_sto.json"
    json_str = json.dumps(yosys_json, indent=2)
    Path(json_path).write_text(json_str, encoding="utf-8")
    print(f"  Saved: {json_path}")
    print(f"\n  --- Generated JSON ---")
    print(json_str)

    # --- Step 4: Verify net IDs ---
    verify_net_ids(yosys_json)

    # --- Step 5: Run netlistsvg ---
    print("\n[4/4] Attempting SVG rendering via netlistsvg...")
    if check_node_installed():
        svg_path = "test_sto.svg"
        success = run_netlistsvg(json_path, svg_path, skin_path)
        if success:
            print(f"\n  SUCCESS: Open {svg_path} in a browser to inspect the result.")
        else:
            print("\n  FAILED: netlistsvg returned an error. Check the JSON structure.")
    else:
        print("\n  SKIPPED: Install Node.js, then re-run this script.")
        print(f"  You can also run manually:")
        print(f"    npx netlistsvg {json_path} -o test_sto.svg --skin {skin_path}")

    print("\n" + "=" * 60)
    print("  PoC complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
