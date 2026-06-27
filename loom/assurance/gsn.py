"""GSN assurance-case skeleton generation (HANDOFF §8 M5).

Builds a Goal Structuring Notation argument that the composed vehicle is
acceptably safe, assembled from the composition + contracts + static-check
results + runtime-monitor outcomes + the swap-gate record. Machine-readable
(YAML) first, rendered to Mermaid second.

This is a generated **skeleton** — the argument structure and evidence pointers,
not a reviewed, complete, or certified safety case (HANDOFF §10 principle 7, §11).
A goal is marked *defeated* when its evidence fails (a static error, or a runtime
monitor violation), so the argument honestly reflects the run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class GsnNode:
    id: str
    type: str  # goal | strategy | solution | context | assumption
    text: str
    status: str = "supported"  # supported | defeated


@dataclass
class GsnLink:
    source: str
    target: str
    kind: str  # supportedBy | inContextOf


@dataclass
class Gsn:
    nodes: list[GsnNode] = field(default_factory=list)
    links: list[GsnLink] = field(default_factory=list)

    def add(self, node: GsnNode) -> GsnNode:
        self.nodes.append(node)
        return node

    def link(self, source: str, target: str, kind: str) -> None:
        self.links.append(GsnLink(source, target, kind))

    @property
    def defeated(self) -> list[GsnNode]:
        return [n for n in self.nodes if n.status == "defeated"]

    def to_dict(self) -> dict:
        return {
            "nodes": [{"id": n.id, "type": n.type, "text": n.text, "status": n.status} for n in self.nodes],
            "links": [{"from": l.source, "to": l.target, "kind": l.kind} for l in self.links],
        }


def build_gsn(comp, modules, report, violations, revalidated_swaps=None) -> Gsn:
    g = Gsn()
    viol_by_module: dict[str, list] = {}
    for v in violations:
        viol_by_module.setdefault(v.module, []).append(v)

    top = g.add(GsnNode("G1", "goal", f"Vehicle '{comp.name}' is acceptably safe within its declared ODD."))
    g.add(GsnNode("C1", "context", f"vehicleClass={comp.vehicle_class}, VSS={comp.vss_release}, plant={comp.plant_impl}"))
    g.link("G1", "C1", "inContextOf")
    g.add(GsnNode("S1", "strategy", "Argue over each subsystem's safety contract and the composition checks."))
    g.link("G1", "S1", "supportedBy")

    static_ok = report.ok
    g.add(GsnNode("G-static", "goal", "The composition is internally compatible.",
                  status="supported" if static_ok else "defeated"))
    g.link("S1", "G-static", "supportedBy")
    g.add(GsnNode("Sn-static", "solution",
                  f"Static check: {len(report.errors)} error(s), {len(report.warnings)} warning(s).",
                  status="supported" if static_ok else "defeated"))
    g.link("G-static", "Sn-static", "supportedBy")

    for m in modules:
        c = m.contract
        sub = m.subsystem
        vs = viol_by_module.get(m.module_id, [])
        defeated = bool(vs)
        g.add(GsnNode(f"G-{sub}", "goal", f"{m.module_id} [{c.safety_level}] meets its contract.",
                      status="defeated" if defeated else "supported"))
        g.link("S1", f"G-{sub}", "supportedBy")
        for i, assumption in enumerate(c.assume):
            g.add(GsnNode(f"A-{sub}-{i}", "assumption", assumption))
            g.link(f"G-{sub}", f"A-{sub}-{i}", "inContextOf")
        if vs:
            ids = "; ".join(sorted({v.monitor_id for v in vs}))
            g.add(GsnNode(f"Sn-mon-{sub}", "solution", f"Runtime monitor: {len(vs)} violation(s) [{ids}].", status="defeated"))
        else:
            g.add(GsnNode(f"Sn-mon-{sub}", "solution", "Runtime monitors: no violation observed."))
        g.link(f"G-{sub}", f"Sn-mon-{sub}", "supportedBy")

    if revalidated_swaps:
        g.add(GsnNode("G-swap", "goal", "Below-line implementation swaps were re-validated."))
        g.link("S1", "G-swap", "supportedBy")
        g.add(GsnNode("Sn-swap", "solution", "Re-validated: " + "; ".join(s.describe() for s in revalidated_swaps)))
        g.link("G-swap", "Sn-swap", "supportedBy")

    if g.defeated:
        top.status = "defeated"
    return g


_SHAPE = {
    "goal": ("[", "]"),
    "strategy": ("[/", "/]"),
    "solution": ("((", "))"),
    "context": ("([", "])"),
    "assumption": ("{{", "}}"),
}


def _san(text: str) -> str:
    """Make label text safe for a quoted Mermaid node label: drop bracket/brace
    chars that conflict with node-shape syntax, normalize quotes, and neutralize
    angle brackets / ampersands that Mermaid's HTML labels mis-handle."""
    text = text.replace('"', "'").replace("\n", " ")
    text = text.replace("<", "‹").replace(">", "›").replace("&", " and ")
    return re.sub(r"[\[\]{}()|]", "", text).strip()


def render_mermaid(g: Gsn) -> str:
    lines = ["flowchart TD"]
    for n in g.nodes:
        open_, close_ = _SHAPE.get(n.type, ("[", "]"))
        lines.append(f'  {n.id}{open_}"{_san(n.text)}"{close_}')
    for link in g.links:
        arrow = "-. context .->" if link.kind == "inContextOf" else "-->"
        lines.append(f"  {link.source} {arrow} {link.target}")
    defeated = [n.id for n in g.defeated]
    if defeated:
        lines.append("  classDef defeated fill:#fdd,stroke:#c00,stroke-width:2px;")
        lines.append(f"  class {','.join(defeated)} defeated;")
    return "\n".join(lines)
