"""Wire router — orthogonal routing between component anchors with obstacle avoidance.

Routes wires using L-shaped (one bend) or Z-shaped (two bend) paths.
Maintains an occupancy grid to avoid routing through component bodies.
Inserts junction dots where multiple wires meet at the same point.
"""

from dataclasses import dataclass
import schemdraw.elements as elm

from .placer import Placement
from .components import COMPONENT_SIZES


# How much clearance (in grid units) to leave around components
CLEARANCE = 0.5


@dataclass
class WireSegment:
    """A straight wire segment from start to end."""
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass
class WireRoute:
    """A complete wire route (one or more segments)."""
    segments: list[WireSegment]


def route_wires(connections, drawn_elements, placements, graph,
                x_adjustments=None):
    """Compute wire routes for all connections.

    Args:
        connections: List of (src_pos, tgt_pos) tuples
        drawn_elements: Dict of component name -> drawn Schemdraw element
        placements: Dict of component name -> Placement
        graph: The CircuitGraph
        x_adjustments: Dict of component name -> X offset (e.g., transistor alignment)

    Returns:
        Tuple of (routes: list[WireRoute], junctions: set of (x,y) points)
    """
    # Build occupancy set: bounding boxes of all placed components
    occupied = _build_occupancy(placements, graph, x_adjustments or {})

    routes = []
    # Track all wire endpoints for junction detection
    wire_endpoints = {}  # (x,y) rounded -> count of wires touching this point

    for src_pos, tgt_pos in connections:
        if src_pos is None or tgt_pos is None:
            continue

        route = _route_single(src_pos, tgt_pos, occupied)
        routes.append(route)

        # Track wire start/end points (not internal bends) for junction detection.
        # Each wire contributes its two endpoints (src_pos, tgt_pos) — not
        # intermediate bend points, which are routing artifacts.
        for pt in [src_pos, tgt_pos]:
            key = _round_pt(pt)
            wire_endpoints[key] = wire_endpoints.get(key, 0) + 1

    # Junctions: points where 3+ distinct wires meet (true T-junctions)
    junctions = {pt for pt, count in wire_endpoints.items() if count >= 3}

    return routes, junctions


def _route_single(src, tgt, occupied):
    """Route a single wire between two points.

    Strategy:
    1. If aligned (same x or same y) — straight line
    2. Try L-route (horizontal then vertical, or vertical then horizontal)
    3. If L-route corner is occupied — use Z-route (3 segments)
    """
    sx, sy = src
    tx, ty = tgt

    # Same point
    if abs(sx - tx) < 0.01 and abs(sy - ty) < 0.01:
        return WireRoute(segments=[])

    # Straight line (aligned) — check if it passes through a component
    if abs(sy - ty) < 0.01 or abs(sx - tx) < 0.01:
        if not _segment_hits_box(src, tgt, occupied):
            return WireRoute(segments=[WireSegment(src, tgt)])

    # Try L-route: horizontal first, then vertical
    corner_hv = (tx, sy)
    if (not _is_occupied(corner_hv, occupied)
            and not _segment_hits_box(src, corner_hv, occupied)
            and not _segment_hits_box(corner_hv, tgt, occupied)):
        return WireRoute(segments=[
            WireSegment(src, corner_hv),
            WireSegment(corner_hv, tgt),
        ])

    # Try L-route: vertical first, then horizontal
    corner_vh = (sx, ty)
    if (not _is_occupied(corner_vh, occupied)
            and not _segment_hits_box(src, corner_vh, occupied)
            and not _segment_hits_box(corner_vh, tgt, occupied)):
        return WireRoute(segments=[
            WireSegment(src, corner_vh),
            WireSegment(corner_vh, tgt),
        ])

    # Z-route: try several horizontal offsets to find a clear channel
    for offset_frac in [0.5, 0.3, 0.7, 0.2, 0.8]:
        mid_x = sx + offset_frac * (tx - sx)
        mid1 = (mid_x, sy)
        mid2 = (mid_x, ty)
        if (not _segment_hits_box(src, mid1, occupied)
                and not _segment_hits_box(mid1, mid2, occupied)
                and not _segment_hits_box(mid2, tgt, occupied)):
            return WireRoute(segments=[
                WireSegment(src, mid1),
                WireSegment(mid1, mid2),
                WireSegment(mid2, tgt),
            ])

    # Fallback: Z-route at midpoint even if it clips (better than nothing)
    mid_x = (sx + tx) / 2
    mid1 = (mid_x, sy)
    mid2 = (mid_x, ty)
    return WireRoute(segments=[
        WireSegment(src, mid1),
        WireSegment(mid1, mid2),
        WireSegment(mid2, tgt),
    ])


def _build_occupancy(placements, graph, x_adjustments=None):
    """Build a list of bounding boxes for all placed components."""
    if x_adjustments is None:
        x_adjustments = {}
    boxes = []
    for name, placement in placements.items():
        comp_info = graph.components.get(name)
        if not comp_info:
            continue

        comp_type = comp_info.comp_type
        size = COMPONENT_SIZES.get(comp_type, (3.0, 1.0))

        # Apply the same X adjustments the renderer uses (e.g., transistor alignment)
        x = placement.x + x_adjustments.get(name, 0)
        y = placement.y
        if placement.orientation == "down":
            # Component extends downward from (x, y)
            w = size[1] / 2 + CLEARANCE
            h = size[0] + CLEARANCE
            boxes.append((x - w, y - h - CLEARANCE, x + w, y + CLEARANCE))
        elif placement.orientation == "right":
            w = size[0] + CLEARANCE
            h = size[1] / 2 + CLEARANCE
            boxes.append((x - CLEARANCE, y - h, x + w, y + h))
        elif placement.orientation == "up":
            w = size[1] / 2 + CLEARANCE
            h = size[0] + CLEARANCE
            boxes.append((x - w, y - CLEARANCE, x + w, y + h + CLEARANCE))
        elif placement.orientation == "left":
            w = size[0] + CLEARANCE
            h = size[1] / 2 + CLEARANCE
            boxes.append((x - w, y - h, x + CLEARANCE, y + h))

    return boxes


def _is_occupied(point, boxes):
    """Check if a point falls inside any component bounding box."""
    px, py = point
    for x1, y1, x2, y2 in boxes:
        if x1 < px < x2 and y1 < py < y2:
            return True
    return False


def _segment_hits_box(p1, p2, boxes):
    """Check if a straight wire segment from p1 to p2 passes through any box.

    Samples points along the segment and checks occupancy.
    """
    x1, y1 = p1
    x2, y2 = p2
    steps = max(int(max(abs(x2 - x1), abs(y2 - y1)) / 0.5), 2)
    for i in range(1, steps):
        t = i / steps
        px = x1 + t * (x2 - x1)
        py = y1 + t * (y2 - y1)
        if _is_occupied((px, py), boxes):
            return True
    return False


def _round_pt(pt):
    """Round point coordinates for junction detection."""
    return (round(pt[0], 2), round(pt[1], 2))


def draw_routes(d, routes, junctions):
    """Draw computed wire routes and junction dots onto a Schemdraw drawing.

    Args:
        d: Schemdraw Drawing object
        routes: List of WireRoute objects
        junctions: Set of (x, y) points where junction dots should be placed
    """
    for route in routes:
        for seg in route.segments:
            d.add(elm.Line().at(seg.start).to(seg.end))

    for pt in junctions:
        d.add(elm.Dot().at(pt))
