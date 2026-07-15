"""Append-only JSONL event log + deterministik replay. I/O yalnizca bu pakette.
Log-first durability: append (tam satir) -> fsync -> sonra turetilmis gorunum (ADR-003)."""
