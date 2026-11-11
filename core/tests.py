import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.alerts import send_alert
from core.management.commands import backup_data


class AlertTests(TestCase):
    @override_settings(ALERT_EMAIL="a@example.com, b@example.com", DEFAULT_FROM_EMAIL="no-reply@example.com")
    def test_alert_goes_to_every_address(self):
        self.assertTrue(send_alert("Teste", "corpo"))
        self.assertEqual(mail.outbox[0].to, ["a@example.com", "b@example.com"])
        self.assertEqual(mail.outbox[0].subject, "[Confin] Teste")
        self.assertEqual(mail.outbox[0].from_email, "no-reply@example.com")

    @override_settings(ALERT_EMAIL="")
    def test_no_recipient_does_not_raise(self):
        self.assertFalse(send_alert("Teste", "corpo"))
        self.assertEqual(mail.outbox, [])


class BackupTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def touch(self, name):
        (self.dir / name).write_bytes(b"x")

    def test_prune_keeps_recent_days_and_first_of_month(self):
        for name in ("db-20261110-033000.dump", "files-20261110-033000.tar.gz",   # ontem
                     "db-20261020-033000.dump",                                    # antigo, dia comum
                     "db-20261001-033000.dump", "files-20261001-033000.tar.gz",   # antigo, dia 1
                     "db-20250901-033000.dump",                                    # dia 1, mas há mais de 12 meses
                     "outro-arquivo.txt"):
            self.touch(name)
        removed = backup_data.prune(self.dir, datetime(2026, 11, 11, 3, 30), keep_days=14, keep_months=12)
        self.assertEqual(sorted(removed), ["db-20250901-033000.dump", "db-20261020-033000.dump"])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ["db-20261001-033000.dump", "db-20261110-033000.dump", "files-20261001-033000.tar.gz",
                          "files-20261110-033000.tar.gz", "outro-arquivo.txt"])

    def test_files_are_archived(self):
        import tarfile

        storage = self.dir / "storage"
        storage.mkdir()
        (storage / "fatura.pdf").write_bytes(b"%PDF")
        with override_settings(ASSISTANT_STORAGE_DIR=storage):
            target = backup_data.backup_files(self.dir, "20261111-033000")
        with tarfile.open(target) as tar:
            self.assertIn("storage/fatura.pdf", tar.getnames())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    @override_settings(ALERT_EMAIL="a@example.com")
    def test_failure_sends_alert_and_fails_the_command(self):
        with mock.patch.object(backup_data, "backup_database", side_effect=CommandError("pg_dump falhou: sem acesso")):
            with self.assertRaises(CommandError):
                call_command("backup_data", dir=str(self.dir))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Backup falhou", mail.outbox[0].subject)
        self.assertIn("sem acesso", mail.outbox[0].body)

    def test_success_writes_database_and_reports(self):
        from io import StringIO

        def fake_db(directory, stamp):
            path = directory / f"db-{stamp}.dump"
            path.write_bytes(b"dump")
            return path

        out = StringIO()
        with mock.patch.object(backup_data, "backup_database", side_effect=fake_db), \
                override_settings(ASSISTANT_STORAGE_DIR=self.dir / "nao-existe"):
            call_command("backup_data", dir=str(self.dir), stdout=out)
        self.assertEqual(len(list(self.dir.glob("db-*.dump"))), 1)
        self.assertIn("db-", out.getvalue())
        self.assertEqual(mail.outbox, [])
