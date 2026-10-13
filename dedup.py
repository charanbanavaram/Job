"""
Deduplication Manager
Maintains and updates seen_jobs.txt to ensure no job is ever alerted or processed twice.
"""

import os
from typing import Set

DEFAULT_SEEN_FILE = "seen_jobs.txt"


class DeduplicationManager:
    def __init__(self, filepath: str = DEFAULT_SEEN_FILE):
        self.filepath = filepath
        self.seen_ids: Set[str] = self._load()

    def _load(self) -> Set[str]:
        if not os.path.exists(self.filepath):
            # Create an empty file if it doesn't exist
            with open(self.filepath, "w", encoding="utf-8") as f:
                pass
            return set()

        with open(self.filepath, "r", encoding="utf-8") as f:
            ids = {line.strip() for line in f if line.strip() and not line.startswith("#")}
        return ids

    def is_seen(self, job_id: str) -> bool:
        return job_id in self.seen_ids

    def mark_seen(self, job_id: str) -> None:
        if job_id not in self.seen_ids:
            self.seen_ids.add(job_id)
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(f"{job_id}\n")

    def mark_seen_batch(self, job_ids: Set[str]) -> None:
        new_ids = job_ids - self.seen_ids
        if new_ids:
            self.seen_ids.update(new_ids)
            with open(self.filepath, "a", encoding="utf-8") as f:
                for jid in new_ids:
                    f.write(f"{jid}\n")

    def count(self) -> int:
        return len(self.seen_ids)
