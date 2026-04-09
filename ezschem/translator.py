"""Translate ezschem parts/nets into Yosys JSON for netlistsvg rendering."""

import json
import os
import shutil
import subprocess
import urllib.request
from collections import defaultdict
from pathlib import Path

from .components import (
    ANCHOR_ALIASES, DEFAULT_PINS, POWER_NETS, GROUND_NETS,
    resolve_anchor,
)

# ---------------------------------------------------------------------------
# Type and pin mapping: ezschem → netlistsvg skin
# ---------------------------------------------------------------------------

# Maps ezschem types to netlistsvg skin ALIAS values (not s:type names).
# netlistsvg matches cells by alias, not by the s:type attribute.
SKIN_TYPES = {
    "res": "r_v",
    "cap": "c_v",
    "ind": "l_v",
    "diode": "d_v",
    "led": "d_led_v",
    "zener": "d_sk_v",
    "npn": "q_npn",
    "pnp": "q_pnp",
    "nmos": "nmos",    # alias added to q_npn block in patched skin
    "pmos": "pmos",    # alias added to q_pnp block in patched skin
    "opamp": "opamp",
    "sw": "r_v",
}

# Maps resolved ezschem pin names → netlistsvg skin port IDs.
# NMOS/PMOS skin symbols reuse NPN/PNP port layout (C/B/E).
# Pin mapping is per-skin-type since port IDs differ across component families.
# Passives (r_v, c_v, l_v) use A/B; diodes use +/-; transistors use C/B/E.
_PASSIVE_PORTS = {"start": "A", "end": "B"}
_DIODE_PORTS = {"start": "+", "end": "-"}
_BJT_PORTS = {"collector": "C", "base": "B", "emitter": "E"}
_FET_PORTS = {"drain": "C", "gate": "B", "source": "E"}
_OPAMP_PORTS = {"in1": "+", "in2": "-", "out": "OUT"}

_PIN_TO_PORT_BY_TYPE = {
    "res": _PASSIVE_PORTS, "cap": _PASSIVE_PORTS, "ind": _PASSIVE_PORTS,
    "sw": _PASSIVE_PORTS,
    "diode": _DIODE_PORTS, "led": _DIODE_PORTS, "zener": _DIODE_PORTS,
    "npn": _BJT_PORTS, "pnp": _BJT_PORTS,
    "nmos": _FET_PORTS, "pmos": _FET_PORTS,
    "opamp": _OPAMP_PORTS,
}


def _pin_to_port(comp_type: str, pin_name: str) -> str:
    """Map an ezschem pin name to a netlistsvg skin port ID."""
    ports = _PIN_TO_PORT_BY_TYPE.get(comp_type, {})
    return ports.get(pin_name, pin_name)

# Skin types that should be oriented vertically by ELK.
VERTICAL_TYPES = {"r_v", "c_v", "l_v", "diode_v", "vcc", "gnd"}


# ---------------------------------------------------------------------------
# Skin file management
# ---------------------------------------------------------------------------

_SKIN_URL = (
    "https://raw.githubusercontent.com/nturley/netlistsvg/master/lib/analog.svg"
)

# NMOS/PMOS standalone blocks (not matched by netlistsvg currently, but kept
# for future skin-parser fixes). The aliases on NPN/PNP are what actually work.
_NMOS_SVG = '''
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

_PMOS_SVG = '''
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


def _skin_dir() -> Path:
    """Return the directory where the skin file is cached (next to this module)."""
    return Path(__file__).parent


def ensure_skin() -> Path:
    """Ensure the custom analog skin file exists; download and patch if needed.

    Returns:
        Path to the skin SVG file.

    Raises:
        RuntimeError: If the skin cannot be downloaded.
    """
    skin_path = _skin_dir() / "analog_skin.svg"
    if skin_path.exists():
        return skin_path

    try:
        req = urllib.request.Request(_SKIN_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            svg = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(
            f"Failed to download netlistsvg analog skin: {e}\n"
            f"Manually download from {_SKIN_URL} and save as {skin_path}"
        ) from e

    # Add nmos/pmos aliases to existing NPN/PNP blocks
    svg = svg.replace(
        '<s:alias val="q_npn"/>',
        '<s:alias val="q_npn"/>\n  <s:alias val="nmos"/>',
    )
    svg = svg.replace(
        '<s:alias val="q_pnp"/>',
        '<s:alias val="q_pnp"/>\n  <s:alias val="pmos"/>',
    )

    # Inject standalone NMOS/PMOS blocks
    svg = svg.replace("</svg>", _NMOS_SVG + _PMOS_SVG + "</svg>")

    skin_path.write_text(svg, encoding="utf-8")
    return skin_path


# ---------------------------------------------------------------------------
# Net ID allocator (union-find)
# ---------------------------------------------------------------------------

class _NetIdAllocator:
    """Assigns unique integer IDs to net nodes, merging connected nets."""

    def __init__(self):
        self._next_id = 2  # 0/1 reserved by convention
        self._map: dict[str, int] = {}

    def get_or_create(self, key: str) -> int:
        if key not in self._map:
            self._map[key] = self._next_id
            self._next_id += 1
        return self._map[key]

    def unify(self, a: str, b: str) -> int:
        id_a = self._map.get(a)
        id_b = self._map.get(b)
        if id_a is not None and id_b is not None:
            if id_a != id_b:
                for k in self._map:
                    if self._map[k] == id_b:
                        self._map[k] = id_a
            return id_a
        if id_a is not None:
            self._map[b] = id_a
            return id_a
        if id_b is not None:
            self._map[a] = id_b
            return id_b
        nid = self._next_id
        self._next_id += 1
        self._map[a] = nid
        self._map[b] = nid
        return nid

    def dump(self) -> dict[str, int]:
        return dict(self._map)


# ---------------------------------------------------------------------------
# Translator: parts + nets → Yosys JSON dict
# ---------------------------------------------------------------------------

def _parse_token(token: str, parts: dict) -> tuple[str, str | None]:
    """Parse 'Q1.D' → ('Q1', 'drain') or 'Vcc' → ('Vcc', None)."""
    if "." in token:
        comp_name, alias = token.split(".", 1)
        if comp_name not in parts:
            raise ValueError(f"Component '{comp_name}' not in parts dict")
        resolved = resolve_anchor(parts[comp_name][0], alias)
        return comp_name, resolved
    return token, None


def _pin_key(name: str, pin: str | None) -> str:
    return f"{name}.{pin}" if pin else name


def to_yosys_json(parts: dict, nets: list[str],
                   hints: dict | None = None,
                   module_name: str = "circuit") -> dict:
    """Translate ezschem parts/nets into a Yosys-format JSON netlist.

    Args:
        parts: {"R1": ("res", "10k"), "Q1": ("nmos",), ...}
        nets: ["Vcc -> R1 -> Q1.D", "Q1.S -> GND", ...]
        hints: Reserved for future use (layout hints).
        module_name: Top-level module name.

    Returns:
        dict suitable for json.dumps() → netlistsvg input.
    """
    hints = hints or {}
    alloc = _NetIdAllocator()
    use_counts: dict[str, int] = {}
    supply_instances: list[tuple[str, int]] = []
    signal_nets: set[str] = set()

    # --- Pass 1: walk chains, assign/unify net IDs ---
    for net_str in nets:
        tokens = [t.strip() for t in net_str.split("->")]
        if len(tokens) < 2:
            raise ValueError(f"Net must have >= 2 nodes: '{net_str}'")

        prev: str | None = None

        for token in tokens:
            name, pin = _parse_token(token, parts)
            is_supply = name in POWER_NETS or name in GROUND_NETS

            # Supply nets are local symbols — don't unify globally
            if is_supply:
                if prev is not None:
                    nid = alloc.get_or_create(prev)
                    supply_instances.append((name, nid))
                    prev = None
                else:
                    fresh = f"__supply_{len(supply_instances)}__"
                    alloc.get_or_create(fresh)
                    supply_instances.append((name, alloc.get_or_create(fresh)))
                    prev = fresh
                continue

            if name in parts:
                if pin is not None:
                    # Explicit pin
                    key = _pin_key(name, pin)
                    alloc.get_or_create(key)
                    if prev is not None:
                        alloc.unify(prev, key)
                    prev = key
                else:
                    # Two-terminal pass-through
                    defaults = DEFAULT_PINS.get(parts[name][0])
                    if defaults is None:
                        raise ValueError(
                            f"Component '{name}' ({parts[name][0]}) requires "
                            f"explicit pin (e.g., '{name}.B')"
                        )
                    entry = _pin_key(name, defaults[0])
                    exit_ = _pin_key(name, defaults[1])
                    alloc.get_or_create(entry)
                    alloc.get_or_create(exit_)
                    if prev is not None:
                        alloc.unify(prev, entry)
                    prev = exit_
            else:
                # Signal net node (STO_A, MOTOR_OUT, Vin, Vout, etc.)
                key = _pin_key(name, None)
                signal_nets.add(name)
                alloc.get_or_create(key)
                if prev is not None:
                    alloc.unify(prev, key)
                prev = key

    # --- Pass 2: build cells ---
    net_map = alloc.dump()
    cells: dict = {}

    for comp_name, spec in parts.items():
        comp_type = spec[0]
        value = spec[1] if len(spec) > 1 else None
        skin_type = SKIN_TYPES.get(comp_type, "generic")

        connections = {}
        port_dirs = {}
        for full_key, nid in net_map.items():
            if "." not in full_key:
                continue
            key_comp, key_pin = full_key.split(".", 1)
            if key_comp != comp_name:
                continue
            port = _pin_to_port(comp_type, key_pin)
            connections[port] = [nid]
            if key_pin in ("start", "collector", "drain", "in1", "in2"):
                port_dirs[port] = "input"
            else:
                port_dirs[port] = "output"

        attrs: dict = {"ref": comp_name}
        if value:
            attrs["value"] = value
        if skin_type in VERTICAL_TYPES:
            attrs["org.eclipse.elk.direction"] = "DOWN"

        cells[comp_name] = {
            "type": skin_type,
            "port_directions": port_dirs,
            "connections": connections,
            "attributes": attrs,
        }

    # --- Pass 3: local supply symbols ---
    supply_count: dict[str, int] = defaultdict(int)
    for supply_name, nid in supply_instances:
        resolved = nid
        for v in net_map.values():
            if v == nid:
                resolved = v
                break

        supply_count[supply_name] += 1
        cell_name = f"{supply_name}_{supply_count[supply_name]}"
        is_power = supply_name in POWER_NETS
        cells[cell_name] = {
            "type": "vcc" if is_power else "gnd",
            "port_directions": {"A": "output" if is_power else "input"},
            "connections": {"A": [resolved]},
            "attributes": {"ref": supply_name, "org.eclipse.elk.direction": "DOWN"},
        }

    # --- Pass 4: module ports for signal nets ---
    ports = {}
    for name in signal_nets:
        nid = net_map.get(name)
        if nid is not None:
            direction = "output" if "OUT" in name.upper() else "input"
            ports[name] = {"direction": direction, "bits": [nid]}

    return {"modules": {module_name: {"ports": ports, "cells": cells}}}


# ---------------------------------------------------------------------------
# netlistsvg subprocess
# ---------------------------------------------------------------------------

def render_svg(yosys_json: dict, output: str, skin_path: Path) -> str:
    """Write Yosys JSON to a temp file and invoke netlistsvg.

    Args:
        yosys_json: The translated Yosys JSON dict.
        output: Output SVG file path.
        skin_path: Path to the analog skin SVG.

    Returns:
        The output SVG file path.

    Raises:
        RuntimeError: If npx/netlistsvg is not available or fails.
    """
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError(
            "npx not found. Install Node.js: https://nodejs.org/\n"
            "  Windows: winget install OpenJS.NodeJS.LTS\n"
            "  macOS:   brew install node"
        )

    # Write JSON next to the output file
    json_path = Path(output).with_suffix(".json")
    json_path.write_text(json.dumps(yosys_json, indent=2), encoding="utf-8")

    cmd = [npx, "netlistsvg", str(json_path), "-o", output,
           "--skin", str(skin_path)]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        env=dict(os.environ),
    )

    if result.returncode != 0:
        raise RuntimeError(f"netlistsvg failed: {result.stderr.strip()}")

    return output
