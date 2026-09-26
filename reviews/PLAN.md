# Repository review plan

Review branch: `review/accuracy-readability-craft`.
Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`.

## Goal

Review the current implementation from three perspectives: physical and
behavioral accuracy, educational readability, and software craft. A lower
fidelity model is acceptable when its equations and explanations remain
internally consistent within a clearly stated domain.

## Work allocation

- **Primary reviewer — accuracy and synthesis:** trace equations, units,
  conservation, component coupling, numerical integration, and observable
  behavior. Verify specialist claims against authoritative public sources.
  Reproduce important findings and reconcile the other reviews.
- **Readability reviewer:** inspect documentation, naming, module purpose,
  architecture, examples, and the learning path across Python and TypeScript.
- **Craft reviewer:** inspect engine/API/frontend contracts, duplication,
  lifecycle and error handling, tooling, and the value and gaps of tests.

## Sequence

1. Record the clean baseline and create this branch.
2. Run existing Python/frontend checks while reviewers inspect the code.
3. Use targeted experiments for suspected defects; avoid redundant tests.
4. Separate confirmed defects, educational inaccuracies, acceptable
   simplifications, and optional improvements. Give each finding concrete
   evidence, impact, and a proportionate recommendation.
5. Commit a consolidated review with check results and remaining limitations.

## Scope and guardrails

- Review source, tests, examples, configuration, and tracked documentation.
- Preserve implementation during the review so all findings refer to one
  reproducible baseline. Recommendations can be implemented separately.
- Do not treat the absence of higher fidelity physics as a defect by itself.
- Do not demand abstraction or tests unless they solve a concrete problem.
- Keep all deliverables and commits on the review branch; do not publish.

## Completion

All three review passes and the consolidated report are complete. Baseline
checks and focused reproductions are recorded in [README.md](README.md).
Implementation files were preserved. Review servers were stopped after the
browser smoke check. Findings and recommendations are ready for implementation
as separate changes.

A second-pass audit on 2026-09-26 re-verified every finding against the
source with four independent checks, corrected three mischaracterizations
(A7, C3, C6), fixed line references, and added A8–A10, R8, and C8–C10. Its
scope and the full list of changes are in the audit section of
[README.md](README.md).
