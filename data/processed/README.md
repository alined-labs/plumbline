# Processed corpus

The parser's output for every source, committed so that every lane and CI can rebuild the index without running the parser: `make ingest` reads these files, chunks them, takes embeddings from the recordings in `cache/embed/`, and writes the database. Lane D owns this folder.
