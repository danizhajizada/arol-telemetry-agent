"""
Structured report format: goal -> data used -> analyses executed ->
findings -> confidence/limits -> next checks.
Used for the canned report path; the free-text `ask` path has the LLM
follow this same structure directly via its system prompt.
"""
from dataclasses import dataclass, field


@dataclass
class Report:
    goal: str
    data_used: str
    analyses_executed: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    next_checks: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Report: {self.goal}", "", "## Data used", self.data_used, "", "## Analyses executed"]
        lines += [f"- {a}" for a in self.analyses_executed]
        lines += ["", "## Findings"]
        lines += [f"- {f}" for f in self.findings]
        lines += ["", "## Confidence / limits"]
        lines += [f"- {l}" for l in self.limits]
        lines += ["", "## Suggested next checks"]
        lines += [f"- {n}" for n in self.next_checks]
        return "\n".join(lines)
