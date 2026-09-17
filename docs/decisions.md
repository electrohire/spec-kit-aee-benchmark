# Decisions and observed deviations
- 2026-09-17: user explicitly excluded the ZIP. No ZIP content was imported or published.
- Authenticated tbitcs; public ElectroHire repository creation authorized by brief.
- Specify 1.0.0 init uses --integration codex --integration-options=--skills --script py.
  It did not initialize Git. Git was initialized once, with existing author identity.
- extension list --json is unavailable; plain list and installed registry used.
- Evaluator 1.0.0 uses PEP 701 syntax; Python 3.11 failed parsing composition.
  Pin Python 3.12.6. This is a tested requirement, despite bootstrap saying 3.11+.
- Initial fixture phase fixture_smoke was rejected by AEE: only supported lifecycle
  phase names are valid. The failed execution is retained, not counted as success.
- Adapter outputs can collide within one second in a shared project. Automated
  assessments use fresh temporary roots and retain content-addressed copies.
- Use mini-SWE-agent 2.4.6 DefaultAgent with a custom observable Model/Environment
  protocol adapter. Stock batch runner's resume, retry and post-call budget
  behavior do not meet this protocol. One agent history spans treatment phases.
- Related repositories use several licenses; no organization-wide policy found.
  Project licensing is pending. Installed upstream components retain notices.
- No prior shared skills.md was supplied or recovered. Existing installed skills
  were inspected; new controller skills follow local skill-creator guidance.
- Human/controller model costs are unavailable. No API price/model was guessed.

- Evaluator 1.0.0 composition also emits model_routing:null and internal _evaluator_id finding fields inconsistent with its own schema. Adapter retains raw output and removes only these non-contract fields before validating.
