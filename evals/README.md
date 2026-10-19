# Evaluations

- `configs/`: one YAML per configuration (`plumbline.core.config.EvalConfig`), named as in the ablation plan: A0 to A6, E1, R1 and LC. A configuration is identified by its `config_hash()`, which covers behaviour and ignores names.
- `results/<config>/<split>.json`: one `rag_eval.schema.EvalRun` per run, stamped with the config hash, the git SHA and the golden file's hash.
- `baseline.json`: the thresholds the CI evaluation gate enforces. A change needs a written justification and the human's review.
- `calibration/`: the judge's calibration labels and its TPR and TNR table.
- `redteam/`: the red-team configuration and report.

`make eval-retrieval CONFIG=A2 SPLIT=dev` and `make eval CONFIG=A2 SPLIT=dev` run them; `make reproduce` rebuilds every published number from recordings.
