"""Backup do banco de dados e dos arquivos recebidos pelo bot.

    python manage.py backup_data [--dir DIR] [--keep-days 14] [--keep-months 12]

Gera `db-<data>.dump` (PostgreSQL, formato do pg_restore) ou `db-<data>.sqlite3`
e `files-<data>.tar.gz` (ASSISTANT_STORAGE_DIR). Confere o arquivo gerado, apaga
os antigos (mantém os diários recentes e o do dia 1 de cada mês) e avisa por
e-mail se algo falhar.

Restaurar (PostgreSQL):  pg_restore --clean --if-exists --no-owner -d <banco> db-<data>.dump
Restaurar os arquivos:   tar -xzf files-<data>.tar.gz -C <pasta acima de ASSISTANT_STORAGE_DIR>
"""

import os
import re
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.alerts import send_alert

STAMP = "%Y%m%d-%H%M%S"
NAME = re.compile(r"^(db|files)-(\d{8}-\d{6})\.(dump|sqlite3|tar\.gz)$")


def backup_database(directory, stamp):
    db = settings.DATABASES["default"]
    engine = db["ENGINE"].rsplit(".", 1)[-1]
    if engine == "sqlite3":
        target = directory / f"db-{stamp}.sqlite3"
        tmp = target.with_suffix(".partial")
        src = sqlite3.connect(db["NAME"])
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CommandError("a cópia do SQLite não passou na verificação de integridade")
        finally:
            src.close()
            dst.close()
    elif engine == "postgresql":
        target = directory / f"db-{stamp}.dump"
        tmp = target.with_suffix(".partial")
        env = {**os.environ, "PGPASSWORD": str(db.get("PASSWORD") or "")}
        cmd = ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", f"--file={tmp}",
               f"--dbname={db['NAME']}"]
        for flag, key in (("--host", "HOST"), ("--port", "PORT"), ("--username", "USER")):
            if db.get(key):
                cmd.append(f"{flag}={db[key]}")
        run = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if run.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise CommandError(f"pg_dump falhou: {run.stderr.strip()[:500]}")
        # O arquivo abre e tem conteúdo? (lista o índice do dump, sem restaurar)
        check = subprocess.run(["pg_restore", "--list", str(tmp)], capture_output=True, text=True)
        if check.returncode != 0 or "TABLE DATA" not in check.stdout:
            tmp.unlink(missing_ok=True)
            raise CommandError(f"o dump gerado não pôde ser lido: {check.stderr.strip()[:300]}")
    else:
        raise CommandError(f"backup não implementado para o banco '{engine}'")
    os.chmod(tmp, 0o600)
    tmp.rename(target)
    return target


def backup_files(directory, stamp):
    source = Path(settings.ASSISTANT_STORAGE_DIR)
    if not source.is_dir():
        return None
    target = directory / f"files-{stamp}.tar.gz"
    tmp = target.with_suffix(".partial")
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(source, arcname=source.name)  # restaura com: tar -xzf ... -C <pasta acima>
    os.chmod(tmp, 0o600)
    tmp.rename(target)
    return target


def prune(directory, now, keep_days, keep_months):
    """Mantém os backups dos últimos `keep_days` dias e, além deles, o do dia 1 de
    cada mês por `keep_months` meses. Devolve os arquivos apagados."""
    removed = []
    for path in sorted(directory.iterdir()):
        match = NAME.match(path.name)
        if not match:
            continue
        taken = datetime.strptime(match.group(2), STAMP)
        age = now - taken
        if age <= timedelta(days=keep_days):
            continue
        if taken.day == 1 and age <= timedelta(days=31 * keep_months):
            continue
        path.unlink()
        removed.append(path.name)
    return removed


class Command(BaseCommand):
    help = "Backup do banco e dos arquivos recebidos pelo bot, com limpeza dos antigos."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=None, help="Pasta de destino (padrão: BACKUP_DIR).")
        parser.add_argument("--keep-days", type=int, default=14)
        parser.add_argument("--keep-months", type=int, default=12)

    def handle(self, *args, **options):
        directory = Path(options["dir"] or settings.BACKUP_DIR)
        now = datetime.now()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
            stamp = now.strftime(STAMP)
            created = [p for p in (backup_database(directory, stamp), backup_files(directory, stamp)) if p]
            removed = prune(directory, now, options["keep_days"], options["keep_months"])
        except Exception as exc:
            send_alert("Backup falhou", f"O backup de {now:%d/%m/%Y %H:%M} não foi concluído.\n\nErro: {exc}\n\n"
                                        f"Pasta: {directory}\nLog: journalctl -u confin-backup -n 50")
            if isinstance(exc, CommandError):
                raise
            raise CommandError(f"backup falhou: {exc}") from exc
        for path in created:
            self.stdout.write(f"{path} ({path.stat().st_size / 1024:.0f} KB)")
        if removed:
            self.stdout.write(f"Antigos apagados: {len(removed)}")
