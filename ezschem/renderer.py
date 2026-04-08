"""Renderer — converts placed circuit graph into Schemdraw drawing."""

import schemdraw
import schemdraw.elements as elm

from .parser import CircuitGraph
from .placer import Placement
from .components import (
    get_element_class, is_power_net, is_ground_net,
    POWER_SYMBOLS, GROUND_SYMBOLS,
)
from .router import route_wires, draw_routes

# Default label padding — keeps text clear of wires and symbols.
# Note: for .down() elements, Schemdraw rotates loc directions:
#   loc='bottom' = right side in drawing, loc='top' = left side in drawing
LABEL_PAD = 0.225       # Padding between component body and label text
NET_LABEL_PAD = 0.5     # Offset for net node labels (Vin, Vout) from connection point
SUPPLY_LABEL_PAD = 0.3  # Offset for power/ground labels from symbol


def render(graph: CircuitGraph, placements: dict[str, Placement],
           output: str = "circuit.png", dpi: int = 150) -> schemdraw.Drawing:
    """Render the circuit to PNG and/or SVG.

    Args:
        graph: Parsed circuit graph
        placements: Component name -> Placement mapping
        output: Output filename (use .png or .svg extension)
        dpi: Resolution for PNG output

    Returns:
        The Schemdraw Drawing object
    """
    d = schemdraw.Drawing()

    # Track drawn elements by component name for anchor access
    drawn_elements = {}

    # 1a. Compute alignment adjustments: components connected to transistor
    #     collector/emitter need their X shifted to match the actual anchor position.
    #     BJTs have collector/emitter offset from the base (the .at() position).
    x_adjustments = _compute_alignment(graph, placements)

    # 1b. Draw all components at their placed positions (with adjustments)
    for name, info in graph.components.items():
        placement = placements.get(name)
        if placement is None:
            continue

        elem_cls = get_element_class(info.comp_type)
        elem = elem_cls()

        # Set position and orientation
        if placement.orientation == "right":
            elem = elem.right()
        elif placement.orientation == "down":
            elem = elem.down()
        elif placement.orientation == "left":
            elem = elem.left()
        elif placement.orientation == "up":
            elem = elem.up()

        x = placement.x + x_adjustments.get(name, 0)
        elem = elem.at((x, placement.y))

        # Label: ref designator + value, positioned next to the component body
        if info.value:
            label_text = f"{name}\n{info.value}"
        else:
            label_text = name

        # LEDs/diodes have emission arrows on one side — label goes opposite
        has_arrows = info.comp_type in ("led", "diode", "zener")

        if placement.orientation == "down":
            # .down() rotates loc: 'bottom' = right, 'top' = left
            side = 'top' if has_arrows else 'bottom'
            elem = elem.label(label_text, loc=side, ofst=LABEL_PAD)
        elif placement.orientation == "up":
            side = 'bottom' if has_arrows else 'top'
            elem = elem.label(label_text, loc=side, ofst=LABEL_PAD)
        elif placement.orientation == "right":
            # .right() transistors/opamps: 'right' = right side, clear of wires
            elem = elem.label(label_text, loc='right', ofst=LABEL_PAD)
        else:
            elem = elem.label(label_text, loc='top', ofst=LABEL_PAD)

        drawn_elements[name] = d.add(elem)

    # 2. Draw power/ground symbols and collect wire connections
    wire_pairs = []  # list of (src_pos, tgt_pos) for the router

    for conn in graph.connections:
        src_name = conn.source.component
        tgt_name = conn.target.component

        src_pos = _get_anchor_pos(src_name, conn.source.pin, drawn_elements, placements)
        tgt_pos = _get_anchor_pos(tgt_name, conn.target.pin, drawn_elements, placements)

        # Draw local power symbols (Vcc → component)
        if is_power_net(src_name):
            if tgt_pos is not None:
                sym_cls = POWER_SYMBOLS.get(src_name, elm.Vdd)
                d.add(sym_cls().at(tgt_pos).label(src_name, loc='right',
                      ofst=SUPPLY_LABEL_PAD))
            continue

        # Draw local ground symbols (component → GND)
        if is_ground_net(tgt_name):
            if src_pos is not None:
                sym_cls = GROUND_SYMBOLS.get(tgt_name, elm.Ground)
                d.add(sym_cls().at(src_pos))
            continue

        # Handle reversed polarity
        if is_ground_net(src_name):
            if tgt_pos is not None:
                sym_cls = GROUND_SYMBOLS.get(src_name, elm.Ground)
                d.add(sym_cls().at(tgt_pos))
            continue
        if is_power_net(tgt_name):
            if src_pos is not None:
                sym_cls = POWER_SYMBOLS.get(tgt_name, elm.Vdd)
                d.add(sym_cls().at(src_pos).label(tgt_name, loc='right',
                      ofst=SUPPLY_LABEL_PAD))
            continue

        # Collect wire connection for the router
        if src_pos is not None and tgt_pos is not None:
            wire_pairs.append((src_pos, tgt_pos))

    # 2b. Route all wires with obstacle avoidance and junction detection
    routes, junctions = route_wires(wire_pairs, drawn_elements, placements, graph,
                                    x_adjustments=x_adjustments)
    draw_routes(d, routes, junctions)

    # 3. Draw labels for named net nodes (non-supply)
    _draw_net_labels(d, graph, drawn_elements, placements)

    # Save output
    if output.endswith(".svg"):
        d.save(output)
    else:
        d.save(output, dpi=dpi)

    return d


def _compute_alignment(graph, placements):
    """Compute X adjustments so components in the same column as a transistor's
    collector/emitter align vertically with those anchors.

    BJTs drawn with .right() have collector/emitter offset ~0.75 units to the right
    of the base (.at() position). All components in the same vertical chain above
    the collector or below the emitter need to shift right by that offset.
    """
    TRANSISTOR_CE_OFFSET = 0.75

    adjustments = {}
    transistor_types = {"npn", "pnp", "nmos", "pmos"}
    vertical_pins = {"collector", "emitter", "drain", "source"}

    # Build vertical adjacency: component pairs connected by non-horizontal pins
    # in the same column
    vert_neighbors = {}  # comp -> set of comps in same column, vertically connected
    for conn in graph.connections:
        src = conn.source
        tgt = conn.target
        if src.component not in graph.components or tgt.component not in graph.components:
            continue
        src_p = placements.get(src.component)
        tgt_p = placements.get(tgt.component)
        if not src_p or not tgt_p:
            continue
        # Same column check (within tolerance)
        if abs(src_p.x - tgt_p.x) < 1.0:
            vert_neighbors.setdefault(src.component, set()).add(tgt.component)
            vert_neighbors.setdefault(tgt.component, set()).add(src.component)

    # Step 1: Find components directly connected to transistor collector/emitter
    seeds = set()
    for conn in graph.connections:
        src = conn.source
        tgt = conn.target
        if src.component not in graph.components or tgt.component not in graph.components:
            continue
        src_type = graph.components[src.component].comp_type
        tgt_type = graph.components[tgt.component].comp_type

        if src_type in transistor_types and src.pin in vertical_pins:
            if tgt_type not in transistor_types:
                seeds.add(tgt.component)
        if tgt_type in transistor_types and tgt.pin in vertical_pins:
            if src_type not in transistor_types:
                seeds.add(src.component)

    # Step 2: Propagate — any component in the same column connected to a
    # shifted component also gets shifted
    shifted = set(seeds)
    queue = list(seeds)
    while queue:
        current = queue.pop(0)
        for neighbor in vert_neighbors.get(current, []):
            if neighbor not in shifted:
                comp_type = graph.components[neighbor].comp_type
                if comp_type not in transistor_types:
                    shifted.add(neighbor)
                    queue.append(neighbor)

    for comp in shifted:
        adjustments[comp] = TRANSISTOR_CE_OFFSET

    return adjustments


def _get_anchor_pos(comp_name, pin_name, drawn_elements, placements):
    """Get the absolute position of a component's anchor point."""
    if comp_name in drawn_elements and pin_name:
        elem = drawn_elements[comp_name]
        anchor = getattr(elem, pin_name, None)
        if anchor is not None:
            return (anchor[0], anchor[1])

    # For net nodes or fallback: use placement center
    if comp_name in placements:
        p = placements[comp_name]
        return (p.x, p.y)

    return None


def _draw_wire(d, src_pos, tgt_pos):
    """Draw an orthogonal (L-shaped) wire between two points."""
    sx, sy = src_pos
    tx, ty = tgt_pos

    if abs(sx - tx) < 0.01 and abs(sy - ty) < 0.01:
        return  # Same point, no wire needed

    if abs(sy - ty) < 0.01:
        # Horizontal wire
        d.add(elm.Line().at(src_pos).to(tgt_pos))
    elif abs(sx - tx) < 0.01:
        # Vertical wire
        d.add(elm.Line().at(src_pos).to(tgt_pos))
    else:
        # L-shaped: go horizontal first, then vertical
        mid = (tx, sy)
        d.add(elm.Line().at(src_pos).to(mid))
        d.add(elm.Line().at(mid).to(tgt_pos))


def _draw_net_labels(d, graph, drawn_elements, placements):
    """Draw text labels for named net nodes (Vin, Vout, etc.)."""
    for node_name in graph.net_nodes:
        if is_power_net(node_name) or is_ground_net(node_name):
            continue
        # Find where this net node connects — use the first connection point
        for conn in graph.connections:
            pos = None
            if conn.source.component == node_name:
                pos = _get_anchor_pos(
                    conn.target.component, conn.target.pin,
                    drawn_elements, placements
                )
            elif conn.target.component == node_name:
                pos = _get_anchor_pos(
                    conn.source.component, conn.source.pin,
                    drawn_elements, placements
                )
            if pos:
                d.add(elm.Dot(open=True).at(pos))
                # Label above and to the left of the connection point
                label_pos = (pos[0] - NET_LABEL_PAD, pos[1] + NET_LABEL_PAD)
                d.add(elm.Label().at(label_pos).label(node_name))
                break
