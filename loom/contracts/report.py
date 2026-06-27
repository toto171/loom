"""Human-readable rendering of a composition CheckReport (HANDOFF §8 M2)."""
from __future__ import annotations

from loom.contracts.checker import RULES, CheckReport


def render_report(report: CheckReport) -> str:
    lines: list[str] = [f"Composition check — {report.vehicle}"]

    modules = [p for p in report.participants if p.is_module]
    lines.append(f"\nModules ({len(modules)}):")
    for p in modules:
        lines.append(f"  - {p.name}  [{p.safety_level}]  license: {p.license or '(none)'}")

    lines.append("\nSignal graph (producer -> consumers):")
    for edge in report.graph:
        unit = f" [{edge.unit}]" if edge.unit else ""
        producers = ", ".join(edge.producers) if edge.producers else "(no producer)"
        consumers = ", ".join(edge.consumers) if edge.consumers else "(unconsumed)"
        lines.append(f"  {edge.path}{unit}")
        lines.append(f"      {producers}  ->  {consumers}")

    errors_by_rule: dict[str, list] = {}
    warnings_by_rule: dict[str, list] = {}
    for issue in report.issues:
        bucket = errors_by_rule if issue.severity == "error" else warnings_by_rule
        bucket.setdefault(issue.rule, []).append(issue)

    any_resource = any(p.resource for p in report.participants)

    lines.append("\nChecks:")
    for rule in RULES:
        rule_errors = errors_by_rule.get(rule, [])
        rule_warnings = warnings_by_rule.get(rule, [])
        status = "FAIL" if rule_errors else "PASS"
        lines.append(f"  [{status}] {rule}")
        for issue in rule_errors:
            lines.append(f"      ERROR: {issue.message}")
        for issue in rule_warnings:
            lines.append(f"      warn:  {issue.message}")
        if rule == "timing" and not any_resource:
            lines.append(
                "      note:  no timing.resource co-location declared; only "
                "per-module deadline<=period was checked (utilization rule inert)"
            )

    result = "OK" if report.ok else "FAILED"
    lines.append(
        f"\nResult: {result}  ({len(report.errors)} error(s), {len(report.warnings)} warning(s))"
    )
    return "\n".join(lines)
