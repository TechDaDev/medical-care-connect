"""
Backup pruning command.

Usage:
  python manage.py prune_backups                # dry-run
  python manage.py prune_backups --execute       # prune
  python manage.py prune_backups --retain 14
  python manage.py prune_backups --retain-days 30
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Prune old backups by count and/or age."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", default=False)
        parser.add_argument("--retain", type=int, default=0)
        parser.add_argument("--retain-days", type=int, default=0)
        parser.add_argument("--backup-dir", default="")

    def handle(self, *args, **options):
        execute = options["execute"]
        retain = options["retain"] or getattr(settings, "BACKUP_RETENTION_COUNT", 7)
        retain_days = options["retain_days"] or 0
        backup_dir = Path(options["backup-dir"] or getattr(settings, "BACKUP_ROOT", ""))

        if not backup_dir.exists():
            self.stdout.write("No backup directory found.")
            return

        # Collect manifests
        manifests = sorted(
            backup_dir.glob("*.manifest.json"),
            key=lambda p: p.stat().st_mtime, reverse=True
        )

        if not manifests:
            self.stdout.write("No backups to prune.")
            return

        self.stdout.write(f"Found {len(manifests)} backup manifests.")
        self.stdout.write(f"Retain count: {retain}")
        if retain_days:
            self.stdout.write(f"Retain days:  {retain_days}")
        self.stdout.write(f"Dry-run:      {'YES' if not execute else 'NO'}")

        # Keep the latest valid backup no matter what
        always_keep = {manifests[0].stem.replace(".manifest", "")}

        to_prune = []
        cutoff = datetime.now() - timedelta(days=retain_days) if retain_days else None

        for i, mf in enumerate(manifests):
            base = mf.stem.replace(".manifest", "")
            if base in always_keep:
                continue
            if i < retain:
                continue  # Keep within retention count
            # Check age
            if cutoff and datetime.fromtimestamp(mf.stat().st_mtime) > cutoff:
                continue
            dump_file = mf.parent / f"{base}.dump"
            to_prune.append((mf, dump_file))

        if not to_prune:
            self.stdout.write("Nothing to prune.")
            return

        self.stdout.write(f"Will remove {len(to_prune)} backup(s):")
        for mf, df in to_prune:
            self.stdout.write(f"  {df.name}")

        if not execute:
            self.stdout.write(self.style.WARNING("Use --execute to prune."))
            return

        for mf, df in to_prune:
            if df.exists():
                df.unlink()
                self.stdout.write(f"  Removed: {df.name}")
            if mf.exists():
                mf.unlink()
                self.stdout.write(f"  Removed: {mf.name}")

        self.stdout.write(self.style.SUCCESS("Pruning complete."))
