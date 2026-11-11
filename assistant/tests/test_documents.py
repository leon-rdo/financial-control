import io
import tempfile

from django.test import TestCase, override_settings
from pypdf import PdfReader, PdfWriter

from assistant import documents


def make_pdf(password=None):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password, algorithm="AES-256")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class DocumentTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        override = override_settings(ASSISTANT_STORAGE_DIR=self.tmp.name, PDF_PASSWORDS=[])
        override.enable()
        self.addCleanup(override.disable)

    def test_plain_pdf(self):
        saved = documents.save_attachment(None, make_pdf(), "fatura.pdf", "application/pdf")
        self.assertFalse(saved.needs_password)
        self.assertEqual(saved.attachment.kind, "pdf")

    def test_protected_pdf_asks_for_password_and_unlocks(self):
        saved = documents.save_attachment(None, make_pdf("12345"), "fatura.pdf", "application/pdf")
        self.assertTrue(saved.needs_password)
        self.assertFalse(documents.unlock_pdf(saved.attachment, "errada"))
        self.assertTrue(documents.unlock_pdf(saved.attachment, "12345"))
        with open(saved.attachment.storage_path, "rb") as fh:
            self.assertFalse(PdfReader(fh).is_encrypted)

    def test_configured_password_opens_automatically(self):
        with override_settings(PDF_PASSWORDS=["000", "12345"]):
            saved = documents.save_attachment(None, make_pdf("12345"), "fatura.pdf", "application/pdf")
        self.assertFalse(saved.needs_password)

    def test_text_and_unsupported_files(self):
        saved = documents.save_attachment(None, "data;valor\n01/11;10,00".encode("cp1252"), "extrato.csv", None)
        self.assertEqual(saved.attachment.kind, "text")
        with self.assertRaises(documents.DocumentError):
            documents.save_attachment(None, b"x", "audio.ogg", "audio/ogg")
