"""Background jobs (Lane D): the Postgres-backed queue (FOR UPDATE SKIP LOCKED), idempotent
by content hash, and its streamed job events."""
