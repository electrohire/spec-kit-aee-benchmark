# Local measurement index

Both GPUs were verified: RTX 4070 SUPER 12282 MiB and RTX 5060 Ti 16311 MiB.
All benchmark inference used localhost, with $0 API expenditure. Hardware, energy
and controller work are unpriced. The original SWE-bench pilot remains unrun.

- [CPU application/AEE runtime and six-task study](gpu-20260917/README.md), including actual supplemental repairs.
- [Staged TinyDB study](long-horizon-03/README.md): nine dependent checkpoints, no complete hidden milestone passes, all three arms timed out.
- [Interrupted pilot 1](long-horizon-01-interrupted/README.md) and [pilot 2](long-horizon-02-interrupted/README.md), retained as development overhead.

## Complete benchmark-model work inventory

This combines work counts, not success rates or treatment estimates across models.

| Scope | Calls | Known tokens | Calls with unknown usage |
|---|---:|---:|---:|
| [Small-task development smoke](gpu-20260917/coding/development-smoke/hello-call.json) | 1 | 57 | 0 |
| [Small-task primary comparison](gpu-20260917/coding/results.json) | 60 | 247,852 | 0 |
| [Small-task supplemental repairs](gpu-20260917/repair/summary.json) | 13 | 10,132 | 0 |
| [Long-study development smokes](long-horizon-03/setup-accounting.json) | 307 | 5,639,799 | 0 |
| [Interrupted long pilot 1](long-horizon-01-interrupted/summary.json) | 51 | 888,819 | 0 |
| [Interrupted long pilot 2](long-horizon-02-interrupted/summary.json) | 234 | 4,377,753 | 0 |
| [Frozen long comparison including failures](long-horizon-03/summary.json) | 335 | 22,819,457 | 3 |

Total: **1,001 calls; at least 33,983,869 tokens; 3 unknown usages**.
The configured reservation bound is 34,375,606 tokens; this is not an imputed
measured total. See [the ledger](token-ledger.json). Failed work and development
smokes are retained separately from the scored arm denominators.
