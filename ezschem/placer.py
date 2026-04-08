"""Grid placer — assigns (col, row) positions to components using layered graph layout.

Convention: layers map to ROWS (vertical position, top-to-bottom) because
the primary flow in most circuits is power (top) → ground (bottom).
Parallel branches spread horizontally into columns.

Transistor-aware: BJTs/FETs have vertical flow (collector/drain top,
emitter/source bottom) with base/gate branching horizontally.
"""

from collections import defaultdict
from dataclasses import dataclass
from .parser import CircuitGraph, Connection
from .components import is_power_net, is_ground_net, is_supply_net, COMPONENT_SIZES


GRID_SPACING_X = 6.0  # Horizontal spacing between columns
GRID_SPACING_Y = 5.0  # Vertical spacing between rows

# Pin categories for determining edge direction
_VERTICAL_TOP_PINS = {"collector", "drain", "start"}   # Connect upward
_VERTICAL_BOT_PINS = {"emitter", "source", "end"}      # Connect downward
_HORIZONTAL_PINS = {"base", "gate", "in1", "in2", "out"}  # Connect sideways


@dataclass
class Placement:
    """Position and orientation for a placed component."""
    x: float
    y: float
    orientation: str  # "right", "down", "left", "up"


def place(graph: CircuitGraph) -> dict[str, Placement]:
    """Assign grid positions to all components in the circuit.

    Returns:
        Dict mapping component name -> Placement
    """
    components = graph.components
    if not components:
        return {}

    # Build directed adjacency with pin awareness
    # vertical edges: flow top-to-bottom (power→ground direction)
    # horizontal edges: side connections (base/gate)
    vert_forward = defaultdict(set)
    vert_backward = defaultdict(set)
    horiz_edges = []  # (comp_a, comp_b) pairs
    source_comps = set()
    sink_comps = set()

    for conn in graph.connections:
        src_comp = conn.source.component
        tgt_comp = conn.target.component
        src_pin = conn.source.pin
        tgt_pin = conn.target.pin

        if is_power_net(src_comp):
            source_comps.add(tgt_comp)
            continue
        if is_ground_net(tgt_comp):
            sink_comps.add(src_comp)
            continue
        if is_ground_net(src_comp):
            sink_comps.add(tgt_comp)
            continue
        if is_power_net(tgt_comp):
            source_comps.add(src_comp)
            continue

        if src_comp not in components or tgt_comp not in components:
            # Net node connections — treat as horizontal edges
            if src_comp in components and tgt_comp in components:
                pass  # shouldn't happen, but guard
            continue

        # Classify edge direction based on pin types
        is_horiz = (src_pin in _HORIZONTAL_PINS or tgt_pin in _HORIZONTAL_PINS)

        if is_horiz:
            horiz_edges.append((src_comp, tgt_comp))
        else:
            vert_forward[src_comp].add(tgt_comp)
            vert_backward[tgt_comp].add(src_comp)

    comp_names = list(components.keys())

    # Step 1: Assign rows via vertical edges (longest-path from sources)
    rows = _assign_layers(comp_names, vert_forward, vert_backward,
                          source_comps, horiz_edges)

    # Step 2: Assign columns — components connected by horizontal edges
    # should be in the same row but different columns
    row_groups = defaultdict(list)
    for comp, row in rows.items():
        row_groups[row].append(comp)

    cols = _assign_columns(row_groups, vert_forward, vert_backward,
                           horiz_edges, rows)

    # Step 3: Convert to coordinates
    placements = {}
    for comp_name in comp_names:
        row = rows.get(comp_name, 0)
        col = cols.get(comp_name, 0)
        x = col * GRID_SPACING_X
        y = -row * GRID_SPACING_Y

        comp_type = components[comp_name].comp_type
        # BJTs and FETs are naturally vertical with .right() — collector/drain top
        # Two-terminal components need .down() for vertical chains
        if comp_type in ("npn", "pnp", "nmos", "pmos"):
            orientation = "right"
        else:
            orientation = "down"

        placements[comp_name] = Placement(x=x, y=y, orientation=orientation)

    return placements


def _assign_layers(comp_names, forward, backward, source_comps,
                   horiz_edges=()):
    """Assign layer (row) to each component via longest-path from sources."""
    layers = {}

    roots = [c for c in comp_names if c in source_comps or c not in backward]
    if not roots:
        roots = comp_names[:1]

    for comp in roots:
        layers[comp] = 0

    queue = [(comp, 0) for comp in roots]
    while queue:
        current, depth = queue.pop(0)
        for neighbor in forward.get(current, []):
            new_depth = depth + 1
            if layers.get(neighbor, -1) < new_depth:
                layers[neighbor] = new_depth
                queue.append((neighbor, new_depth))

    for comp in comp_names:
        if comp not in layers:
            layers[comp] = 0

    # Post-pass: components connected only by horizontal edges should
    # inherit the row of their horizontal neighbor
    changed = True
    while changed:
        changed = False
        for a, b in horiz_edges:
            if a in layers and b in layers:
                if layers[a] != layers[b]:
                    # Move the one at row 0 (unplaced) to match the other
                    if layers[a] == 0 and a not in source_comps:
                        layers[a] = layers[b]
                        changed = True
                    elif layers[b] == 0 and b not in source_comps:
                        layers[b] = layers[a]
                        changed = True

    return layers


def _assign_columns(row_groups, vert_forward, vert_backward,
                    horiz_edges, rows):
    """Assign column positions within each row.

    Two-pass approach:
    1. Initial assignment top-down with barycenter
    2. Refinement bottom-up to align parents with children
    Then adjust horizontal neighbors to adjacent columns.
    """
    cols = {}
    sorted_rows = sorted(row_groups.keys())

    # Pass 1: top-down — assign based on backward (parent) connections
    for row_idx in sorted_rows:
        comps = row_groups[row_idx]
        _barycenter_assign(comps, cols, vert_backward, vert_forward)

    # Pass 2: bottom-up — refine based on forward (child) connections
    for row_idx in reversed(sorted_rows):
        comps = row_groups[row_idx]
        if len(comps) == 1:
            comp = comps[0]
            child_cols = [cols[n] for n in vert_forward.get(comp, []) if n in cols]
            if child_cols:
                cols[comp] = sum(child_cols) / len(child_cols)

    # Pass 3: ensure horizontal neighbors are in adjacent columns, not same
    for a, b in horiz_edges:
        if a in cols and b in cols:
            if abs(cols[a] - cols[b]) < 0.5:
                cols[b] = cols[a] + 1

    return cols


def _barycenter_assign(comps, cols, backward, forward):
    """Assign columns to components using barycenter of already-placed neighbors."""
    if len(comps) == 1:
        comp = comps[0]
        neighbor_cols = []
        for n in backward.get(comp, []):
            if n in cols:
                neighbor_cols.append(cols[n])
        for n in forward.get(comp, []):
            if n in cols:
                neighbor_cols.append(cols[n])
        cols[comp] = (sum(neighbor_cols) / len(neighbor_cols)) if neighbor_cols else 0
        return

    barycenters = {}
    for comp in comps:
        neighbor_cols = []
        for n in backward.get(comp, []):
            if n in cols:
                neighbor_cols.append(cols[n])
        for n in forward.get(comp, []):
            if n in cols:
                neighbor_cols.append(cols[n])
        barycenters[comp] = (sum(neighbor_cols) / len(neighbor_cols)) if neighbor_cols else 0

    sorted_comps = sorted(comps, key=lambda c: barycenters[c])
    for i, comp in enumerate(sorted_comps):
        cols[comp] = i
