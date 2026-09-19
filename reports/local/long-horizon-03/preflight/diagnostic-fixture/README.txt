Synthetic diagnostic-retention fixture using the pinned .venv-gpu AEE executable.
This is not the original smoke10 stderr: that adapter version failed to retain its subprocess diagnostics.
The original model output and smoke failure remain in smoke10. This fixture independently reproduces the invalid ClaimKind error and verifies that future failures retain the diagnostic artifact. No model calls were made for this fixture.
