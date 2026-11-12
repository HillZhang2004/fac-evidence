# fac evidence

[Tutorial 2 terminal output](fac-tutorial-2-terminal-output.txt)

Open **code.py** to read the original test and **output.txt** to see its inputs, saved commands, stdout, stderr and exit codes.

| Diagnostic | Original code | Saved output |
|---|---|---|
| 1. CLI failure | [code.py](01-cli-failure/code.py) | [output.txt](01-cli-failure/output.txt) |
| 2. JSON Schema | [code.py](02-json-schema/code.py) | [output.txt](02-json-schema/output.txt) |
| 3. Model configuration | [code.py](03-model-config/code.py) | [output.txt](03-model-config/output.txt) |
| 4. Validation retry | [code.py](04-validation-retry/code.py) | [output.txt](04-validation-retry/output.txt) |

Selected master records include the main observation and healthy control. Finding 4 shows invalid-type and healthy sequences, with and without the validation dependency. Other runs remain in the separate full backup.

Code is unchanged and renamed only. Output sections preserve the original bytes, including ANSI styling; stdout/stderr interleaving is not invented. These are inspection copies, not standalone runnable tests; original shared harnesses, fixture paths and runtime dependencies remain external.
