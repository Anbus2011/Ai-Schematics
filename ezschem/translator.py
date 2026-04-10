"""Translate ezschem parts/nets into Yosys JSON for netlistsvg rendering."""

import json
import os
import shutil
import subprocess
import tempfile
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
    "nmos": "nmos",    # alias added to q_npn block in vendored skin
    "pmos": "pmos",    # alias added to q_pnp block in vendored skin
    "opamp": "opamp",
    "sw": "r_v",
}

# Per-type pin mapping: ezschem pin names → netlistsvg skin port IDs.
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

# Paths to vendored netlistsvg
_VENDOR_DIR = Path(__file__).parent / "vendor" / "netlistsvg"
_RENDER_JS = _VENDOR_DIR / "render.js"
_SKIN_PATH = _VENDOR_DIR / "lib" / "analog.svg"

_PARTITION_KEY = "org.eclipse.elk.partitioning.partition"


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
        hints: Optional layout hints per component. Supported keys:
               - "partition": int — ELK partition column ID
               - "x": number — fixed X position (overrides ELK placement)
               - "y": number — fixed Y position (overrides ELK placement)
               Example: {"Q1": {"x": 10, "y": 150}, "Q2": {"x": 160, "y": 150}}
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

        # Apply layout hints
        comp_hints = hints.get(comp_name, {})
        if "partition" in comp_hints:
            attrs[_PARTITION_KEY] = str(comp_hints["partition"])
        if "x" in comp_hints:
            attrs["org.eclipse.elk.x"] = comp_hints["x"]
        if "y" in comp_hints:
            attrs["org.eclipse.elk.y"] = comp_hints["y"]

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

    # --- Pass 4: ensure all cells have partition if any do ---
    # ELK crashes if partitioning is active but some nodes lack the attribute.
    has_partitions = any(
        _PARTITION_KEY in c["attributes"] for c in cells.values()
    )
    if has_partitions:
        for c in cells.values():
            if _PARTITION_KEY not in c["attributes"]:
                c["attributes"][_PARTITION_KEY] = "0"

    # --- Pass 5: module ports for signal nets ---
    ports = {}
    for name in signal_nets:
        nid = net_map.get(name)
        if nid is not None:
            direction = "output" if "OUT" in name.upper() else "input"
            ports[name] = {"direction": direction, "bits": [nid]}

    return {"modules": {module_name: {"ports": ports, "cells": cells}}}


# ---------------------------------------------------------------------------
# netlistsvg subprocess (vendored)
# ---------------------------------------------------------------------------

def render_svg(yosys_json: dict, output: str, skin_path: Path | None = None) -> str:
    """Write Yosys JSON to a temp file and invoke the vendored netlistsvg.

    Args:
        yosys_json: The translated Yosys JSON dict.
        output: Output SVG file path.
        skin_path: Path to the analog skin SVG. Defaults to vendored skin.

    Returns:
        The output SVG file path.

    Raises:
        RuntimeError: If Node.js is not available or netlistsvg fails.
    """
    node = shutil.which("node")
    if not node:
        raise RuntimeError(
            "Node.js not found. Install it:\n"
            "  Windows: winget install OpenJS.NodeJS.LTS\n"
            "  macOS:   brew install node\n"
            "  Linux:   sudo apt install nodejs"
        )

    if skin_path is None:
        skin_path = _SKIN_PATH

    # Ensure output directory exists
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    # Write JSON to a temp file (cleaned up automatically)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as tmp:
        json.dump(yosys_json, tmp, indent=2)
        json_path = tmp.name

    try:
        cmd = [node, str(_RENDER_JS), json_path, output, str(skin_path)]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env=dict(os.environ),
        )

        if result.returncode != 0:
            raise RuntimeError(f"netlistsvg failed: {result.stderr.strip()}")
    finally:
        Path(json_path).unlink(missing_ok=True)

    return output
