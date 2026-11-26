"""Graphviz text and SVG rendering of the dependency graph.

The module turns the graph into three representations:

* Graphviz DOT text, the format used by the ``dot`` tool;
* an SVG picture drawn without any external program: nodes are placed on
  the BFS levels of the graph and connected with arrows;
* an ASCII tree for the terminal.

The SVG document is built with :mod:`xml.etree.ElementTree`, so the
output is always well formed XML with correctly escaped labels."""

import xml.etree.ElementTree as element_tree


SVG_NAMESPACE = "http://www.w3.org/2000/svg"

SVG_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'

NODE_WIDTH = 190

NODE_HEIGHT = 46

COLUMN_GAP = 80

ROW_GAP = 18

MARGIN = 36

FONT_SIZE = 12

FONT_FAMILY = "Helvetica, Arial, sans-serif"

ROOT_FILL = "#dbeafe"

NODE_FILL = "#f8fafc"

NODE_STROKE = "#334155"

EDGE_COLOR = "#64748b"

TEXT_COLOR = "#0f172a"

MAX_LABEL = 26

TRUNCATED = 23

ELLIPSIS = "..."

NO_LEVELS = 0

BRANCH = "├── "

LAST_BRANCH = "└── "

VERTICAL = "│   "

SPACE = "    "

REPEAT = " (повтор)"

def dot_escape(text):
    """Escape a label for the Graphviz DOT language."""
    return text.replace("\\", "\\\\").replace('"', '\\"')

def to_dot(dependency_graph, root_key):
    """Return the Graphviz DOT description of the graph."""
    lines = [
        "digraph dependencies {",
        '    rankdir="LR";',
        '    node [shape=box, style="rounded", fontname="Helvetica"];',
        f'    "{dot_escape(root_key)}" [style="rounded,filled", '
        f'fillcolor="{ROOT_FILL}"];',
    ]
    for key in dependency_graph.order:
        if key == root_key:
            continue
        lines.append(f'    "{dot_escape(key)}";')
    for source, target in dependency_graph.edges:
        lines.append(
            f'    "{dot_escape(source)}" -> "{dot_escape(target)}";')
    lines.append("}")
    return "\n".join(lines) + "\n"

def short_label(key):
    """Shorten a long package label for the picture."""
    if len(key) <= MAX_LABEL:
        return key
    return key[:TRUNCATED] + ELLIPSIS

def layout(dependency_graph):
    """Return the position and the size of every node of the picture."""
    levels = dependency_graph.levels()
    rows = {}
    for key in dependency_graph.order:
        rows.setdefault(levels.get(key, NO_LEVELS), []).append(key)
    positions = {}
    for level, keys in rows.items():
        for index, key in enumerate(keys):
            positions[key] = _position(level, index)
    width = _picture_width(len(rows) - 1)
    height = _picture_height(max((len(keys) for keys in rows.values()),
                                 default=0))
    return positions, width, height

def _position(level, index):
    """Return the top left corner of a node on the given level."""
    left = MARGIN + level * (NODE_WIDTH + COLUMN_GAP)
    top = MARGIN + index * (NODE_HEIGHT + ROW_GAP)
    return left, top

def _picture_width(levels):
    """Return the width of the picture for the number of levels."""
    return MARGIN * 2 + (levels + 1) * NODE_WIDTH + levels * COLUMN_GAP

def _picture_height(rows):
    """Return the height of the picture for the longest level."""
    return MARGIN * 2 + rows * NODE_HEIGHT + (rows - 1) * ROW_GAP

def to_svg(dependency_graph, root_key):
    """Return an SVG document with a layered drawing of the graph."""
    positions, width, height = layout(dependency_graph)
    svg = element_tree.Element("svg", {
        "xmlns": SVG_NAMESPACE,
        "width": str(width),
        "height": str(height),
        "viewBox": f"0 0 {width} {height}",
    })
    _add_marker(svg)
    edges = element_tree.SubElement(svg, "g", {"stroke": EDGE_COLOR,
                                     "fill": "none"})
    for source, target in dependency_graph.edges:
        _add_edge(edges, positions, source, target)
    nodes = element_tree.SubElement(svg, "g")
    for key in dependency_graph.order:
        _add_node(nodes, positions[key], key, key == root_key)
    tree = element_tree.ElementTree(svg)
    element_tree.indent(tree, space="  ")
    return SVG_DECLARATION + element_tree.tostring(svg, encoding="unicode") + "\n"

def _add_marker(svg):
    """Add the arrow head definition used by every edge."""
    defs = element_tree.SubElement(svg, "defs")
    marker = element_tree.SubElement(defs, "marker", {
        "id": "arrow",
        "viewBox": "0 0 10 10",
        "refX": "9",
        "refY": "5",
        "markerWidth": "6",
        "markerHeight": "6",
        "orient": "auto-start-reverse",
    })
    element_tree.SubElement(marker, "path", {
        "d": "M 0 0 L 10 5 L 0 10 z",
        "fill": EDGE_COLOR,
    })

def _add_edge(parent, positions, source, target):
    """Draw one arrow between two nodes."""
    source_left, source_top = positions[source]
    target_left, target_top = positions[target]
    start_x = source_left + NODE_WIDTH
    start_y = source_top + NODE_HEIGHT // 2
    end_x = target_left
    end_y = target_top + NODE_HEIGHT // 2
    element_tree.SubElement(parent, "line", {
        "x1": str(start_x),
        "y1": str(start_y),
        "x2": str(end_x),
        "y2": str(end_y),
        "stroke-width": "1.4",
        "marker-end": "url(#arrow)",
    })

def _add_node(parent, position, key, is_root):
    """Draw one rounded box with the package label."""
    left, top = position
    group = element_tree.SubElement(parent, "g")
    title = element_tree.SubElement(group, "title")
    title.text = key
    element_tree.SubElement(group, "rect", {
        "x": str(left),
        "y": str(top),
        "width": str(NODE_WIDTH),
        "height": str(NODE_HEIGHT),
        "rx": "8",
        "ry": "8",
        "fill": ROOT_FILL if is_root else NODE_FILL,
        "stroke": NODE_STROKE,
        "stroke-width": "1.6" if is_root else "1",
    })
    text = element_tree.SubElement(group, "text", {
        "x": str(left + NODE_WIDTH // 2),
        "y": str(top + NODE_HEIGHT // 2),
        "text-anchor": "middle",
        "dominant-baseline": "central",
        "font-family": FONT_FAMILY,
        "font-size": str(FONT_SIZE),
        "fill": TEXT_COLOR,
    })
    text.text = short_label(key)

def ascii_tree(dependency_graph, root_key):
    """Return the dependency tree of the root package as text lines."""
    lines = [root_key]
    expanded = {root_key}
    stack = []
    _push_children(stack, dependency_graph, root_key, "")
    while stack:
        key, prefix, is_last = stack.pop()
        marker = REPEAT if key in expanded else ""
        branch = LAST_BRANCH if is_last else BRANCH
        lines.append(prefix + branch + key + marker)
        if marker:
            continue
        expanded.add(key)
        indent = prefix + (SPACE if is_last else VERTICAL)
        _push_children(stack, dependency_graph, key, indent)
    return lines

def _push_children(stack, dependency_graph, key, prefix):
    """Push the children of a package so that they pop in order."""
    children = dependency_graph.children(key)
    for index in range(len(children) - 1, -1, -1):
        last = index == len(children) - 1
        stack.append((children[index], prefix, last))

def write_file(path, text):
    """Write a text file in UTF-8."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
