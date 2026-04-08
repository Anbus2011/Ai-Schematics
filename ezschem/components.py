"""Component type mapping and anchor alias resolution for EZSchem."""

import schemdraw.elements as elm


# Maps short type names (used in parts dict) to Schemdraw element classes
COMPONENT_TYPES = {
    "res": elm.Resistor,
    "cap": elm.Capacitor,
    "ind": elm.Inductor,
    "diode": elm.Diode,
    "led": elm.LED,
    "zener": elm.Zener,
    "npn": elm.BjtNpn,
    "pnp": elm.BjtPnp,
    "nmos": elm.NFet,
    "pmos": elm.PFet,
    "opamp": elm.Opamp,
    "sw": elm.Switch,
}

# Maps short anchor aliases to real Schemdraw anchor names, per component type.
# Two-terminal elements (res, cap, ind, diode, led, zener, sw) all share the same mapping.
_TWO_TERMINAL_ANCHORS = {
    "p": "start",    # positive / first
    "n": "end",      # negative / second
    "start": "start",
    "end": "end",
}

_DIODE_ANCHORS = {
    **_TWO_TERMINAL_ANCHORS,
    "A": "start",    # anode
    "K": "end",      # cathode
}

_BJT_ANCHORS = {
    "B": "base",
    "C": "collector",
    "E": "emitter",
    "base": "base",
    "collector": "collector",
    "emitter": "emitter",
}

_FET_ANCHORS = {
    "G": "gate",
    "D": "drain",
    "S": "source",
    "gate": "gate",
    "drain": "drain",
    "source": "source",
}

_OPAMP_ANCHORS = {
    "in1": "in1",    # non-inverting (+)
    "in2": "in2",    # inverting (-)
    "out": "out",
    "vd": "vd",      # positive supply
    "vs": "vs",      # negative supply
}

ANCHOR_ALIASES = {
    "res": _TWO_TERMINAL_ANCHORS,
    "cap": _TWO_TERMINAL_ANCHORS,
    "ind": _TWO_TERMINAL_ANCHORS,
    "sw": _TWO_TERMINAL_ANCHORS,
    "diode": _DIODE_ANCHORS,
    "led": _DIODE_ANCHORS,
    "zener": _DIODE_ANCHORS,
    "npn": _BJT_ANCHORS,
    "pnp": _BJT_ANCHORS,
    "nmos": _FET_ANCHORS,
    "pmos": _FET_ANCHORS,
    "opamp": _OPAMP_ANCHORS,
}

# Default anchors for connection when no pin is specified.
# For two-terminal: first connection uses "start", second uses "end".
# For multi-terminal: no default — pin must be specified.
DEFAULT_PINS = {
    "res": ("start", "end"),
    "cap": ("start", "end"),
    "ind": ("start", "end"),
    "sw": ("start", "end"),
    "diode": ("start", "end"),
    "led": ("start", "end"),
    "zener": ("start", "end"),
}

# Power/ground net names that spawn local symbols
POWER_NETS = {"Vcc", "Vdd", "V+", "VCC", "VDD"}
GROUND_NETS = {"GND", "Vss", "VSS", "V-"}

# Schemdraw elements for power/ground symbols
POWER_SYMBOLS = {
    "Vcc": elm.Vdd,
    "VCC": elm.Vdd,
    "Vdd": elm.Vdd,
    "VDD": elm.Vdd,
    "V+": elm.Vdd,
}

GROUND_SYMBOLS = {
    "GND": elm.Ground,
    "Vss": elm.Ground,
    "VSS": elm.Ground,
    "V-": elm.Ground,
}

# Approximate component sizes (in Schemdraw units) for grid spacing
COMPONENT_SIZES = {
    "res": (3.0, 0.6),
    "cap": (3.0, 0.6),
    "ind": (3.0, 0.8),
    "sw": (3.0, 0.6),
    "diode": (3.0, 0.6),
    "led": (3.0, 0.6),
    "zener": (3.0, 0.6),
    "npn": (1.5, 1.4),
    "pnp": (1.5, 1.4),
    "nmos": (1.5, 1.5),
    "pmos": (1.5, 1.5),
    "opamp": (2.2, 2.5),
}


def resolve_anchor(comp_type: str, alias: str) -> str:
    """Resolve a short anchor alias to the real Schemdraw anchor name.

    Args:
        comp_type: Component type key (e.g., "res", "npn")
        alias: Short alias (e.g., "C") or full name (e.g., "collector")

    Returns:
        Real Schemdraw anchor name

    Raises:
        ValueError: If the alias is not valid for this component type
    """
    aliases = ANCHOR_ALIASES.get(comp_type)
    if aliases is None:
        raise ValueError(f"Unknown component type: {comp_type}")

    real_name = aliases.get(alias)
    if real_name is None:
        valid = sorted(set(aliases.keys()))
        raise ValueError(
            f"Invalid pin '{alias}' for {comp_type}. Valid pins: {', '.join(valid)}"
        )
    return real_name


def get_element_class(comp_type: str):
    """Get the Schemdraw element class for a component type.

    Raises:
        ValueError: If the component type is unknown
    """
    cls = COMPONENT_TYPES.get(comp_type)
    if cls is None:
        valid = sorted(COMPONENT_TYPES.keys())
        raise ValueError(
            f"Unknown component type: '{comp_type}'. Valid types: {', '.join(valid)}"
        )
    return cls


def is_power_net(name: str) -> bool:
    return name in POWER_NETS


def is_ground_net(name: str) -> bool:
    return name in GROUND_NETS


def is_supply_net(name: str) -> bool:
    return is_power_net(name) or is_ground_net(name)
