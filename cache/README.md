# Model-output recordings

Every model call (generation, judging, embedding, reranking, parsing) goes through `plumbline/cache.py`, which stores its response here, content-addressed by the request: `cache/<kind>/<key[:2]>/<key>.json`. Tests, the merge queue and CI replay these files and never call a model, which is why every published number rebuilds with no keys and at no cost. Lanes record new calls with `CACHE_MODE=record` and commit them with their branch. Nothing personal is ever recorded.
