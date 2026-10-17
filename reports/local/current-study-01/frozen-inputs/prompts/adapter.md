Apply the following frozen Spec Kit skill through this mini-SWE-agent adapter.
The issue and repository define the requirements; do not invent product scope.
Code lives in /testbed. Workflow artifacts and pristine Spec Kit scripts/templates
live in /workflow; execute workflow setup scripts from /workflow. Never modify the
upstream repository instructions. Treat /workflow as the project root for skill
artifact paths, and /testbed as the implementation source root. Use python if
python3 is unavailable. Do not spawn agents or request human assistance.
Complete each phase with a done JSON action including artifact references and
summary. Clarify ambiguity using task facts only and preserve remaining assumptions.
After converge, implement any newly found work within the same remaining attempt
budget, rerun convergence and state unresolved gaps. Do not claim tests ran without
command evidence. Optional extension hooks are host-managed only for the AEE arm;
core-only treatment must not invoke extensions.
