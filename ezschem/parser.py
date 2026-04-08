"""Netlist parser — converts parts dict + nets list into an internal circuit graph."""

from dataclasses import dataclass, field
from .components import (
    COMPONENT_TYPES, ANCHOR_ALIASES, DEFAULT_PINS,
    resolve_anchor, is_supply_net,
)


@dataclass
class Pin:
    """A specific pin on a component or a named net node."""
    component: str     # Component name (e.g., "R1") or net node name (e.g., "Vcc")
    pin: str | None    # Pin name (e.g., "C" for collector) or None for net nodes

    @property
    def is_net_node(self) -> bool:
        return self.pin is None and self.component not in _current_parts

    def __repr__(self):
        if self.pin:
            return f"{self.component}.{self.pin}"
        return self.component


@dataclass
class Connection:
    """A wire between two pins."""
    source: Pin
    target: Pin


@dataclass
class ComponentInfo:
    """Parsed component with its type, value, and connections."""
    name: str
    comp_type: str
    value: str | None = None
    connections: list[Connection] = field(default_factory=list)
    # Track which pins have been used for auto-assignment
    _pin_use_count: int = field(default=0, repr=False)


@dataclass
class CircuitGraph:
    """The parsed circuit: components, connections, and net nodes."""
    components: dict[str, ComponentInfo]  # name -> ComponentInfo
    connections: list[Connection]
    net_nodes: set[str]  # Named net nodes (Vin, Vout, etc. — NOT components)


# Module-level ref for Pin.is_net_node — set during parse
_current_parts: dict = {}


def parse(parts: dict, nets: list[str]) -> CircuitGraph:
    """Parse a parts dict and nets list into a CircuitGraph.

    Args:
        parts: Component definitions. Key is ref designator, value is tuple of
               (type,) or (type, value). E.g., {"R1": ("res", "470"), "Q1": ("npn",)}
        nets: Connection strings. E.g., ["Vcc -> R1 -> LED1 -> Q1.C"]

    Returns:
        CircuitGraph with all components, connections, and net nodes.

    Raises:
        ValueError: On invalid component types, pin names, or references.
    """
    global _current_parts
    _current_parts = parts

    # 1. Parse components
    components = {}
    for name, spec in parts.items():
        if not isinstance(spec, (tuple, list)) or len(spec) < 1:
            raise ValueError(f"Invalid part spec for '{name}': expected (type,) or (type, value)")

        comp_type = spec[0]
        value = spec[1] if len(spec) > 1 else None

        if comp_type not in COMPONENT_TYPES:
            valid = sorted(COMPONENT_TYPES.keys())
            raise ValueError(
                f"Unknown component type '{comp_type}' for '{name}'. "
                f"Valid types: {', '.join(valid)}"
            )

        components[name] = ComponentInfo(name=name, comp_type=comp_type, value=value)

    # 2. Parse nets into connections
    connections = []
    net_nodes = set()

    for net_str in nets:
        tokens = [t.strip() for t in net_str.split("->")]
        if len(tokens) < 2:
            raise ValueError(f"Net string must have at least two nodes: '{net_str}'")

        # Parse each token into a Pin
        pins = []
        for token in tokens:
            pin = _parse_token(token, components)
            pins.append(pin)

            # Track net nodes
            if pin.pin is None and pin.component not in components:
                net_nodes.add(pin.component)

        # Create connections between adjacent pins in the chain
        for i in range(len(pins) - 1):
            src = _resolve_pin(pins[i], components, is_source=(i > 0))
            tgt = _resolve_pin(pins[i + 1], components, is_source=False)
            conn = Connection(source=src, target=tgt)
            connections.append(conn)

    return CircuitGraph(
        components=components,
        connections=connections,
        net_nodes=net_nodes,
    )


def _parse_token(token: str, components: dict[str, ComponentInfo]) -> Pin:
    """Parse a net token like 'R1', 'Q1.C', 'Vcc' into a Pin."""
    if "." in token:
        comp_name, pin_alias = token.split(".", 1)
        if comp_name not in components:
            raise ValueError(
                f"Component '{comp_name}' referenced in net but not in parts dict"
            )
        comp_type = components[comp_name].comp_type
        real_pin = resolve_anchor(comp_type, pin_alias)
        return Pin(component=comp_name, pin=real_pin)
    else:
        # Either a component name (no pin specified) or a net node
        return Pin(component=token, pin=None)


def _resolve_pin(pin: Pin, components: dict[str, ComponentInfo],
                 is_source: bool) -> Pin:
    """Resolve a pin that might need auto-assignment of default pins.

    For two-terminal components referenced without a pin name, auto-assign
    start/end based on connection order.
    """
    if pin.pin is not None:
        return pin  # Already has explicit pin

    if pin.component not in components:
        return pin  # Net node — no pin to resolve

    comp = components[pin.component]
    defaults = DEFAULT_PINS.get(comp.comp_type)

    if defaults is None:
        # Multi-terminal component — pin is required
        valid_pins = sorted(set(ANCHOR_ALIASES.get(comp.comp_type, {}).keys()))
        raise ValueError(
            f"Component '{pin.component}' ({comp.comp_type}) requires explicit pin. "
            f"Use e.g., '{pin.component}.{valid_pins[0]}'. "
            f"Valid pins: {', '.join(valid_pins)}"
        )

    # Auto-assign: first use gets start, second gets end
    idx = min(comp._pin_use_count, len(defaults) - 1)
    comp._pin_use_count += 1
    return Pin(component=pin.component, pin=defaults[idx])
