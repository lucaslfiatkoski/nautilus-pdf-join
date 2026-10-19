import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cairo
import gi

gi.require_version("Nautilus", "4.1")
from gi.repository import Gio


class FileInfo:
    def __init__(self, uri, mime="application/pdf", directory=False):
        self.uri, self.mime, self.directory = uri, mime, directory

    def get_location(self):
        return Gio.File.new_for_uri(self.uri)

    def is_mime_type(self, mime):
        return self.mime == mime

    def is_directory(self):
        return self.directory


class MergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("juntar_pdfs.py")
        if not path.exists():
            raise AssertionError("A ação Juntar PDFs ainda não foi implementada")
        spec = importlib.util.spec_from_file_location("juntar_pdfs", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.first = self.folder / "01 orçamento $(teste).pdf"
        self.second = self.folder / "02 contrato.PDF"
        for path, text in [(self.first, "PRIMEIRO"), (self.second, "SEGUNDO")]:
            surface = cairo.PDFSurface(str(path), 300, 200)
            context = cairo.Context(surface)
            context.move_to(20, 50)
            context.show_text(text)
            context.show_page()
            surface.finish()

    def test_menu_only_for_multiple_local_pdfs(self):
        provider = self.module.JuntarPdfsExtension()
        first, second = [FileInfo(p.as_uri()) for p in (self.first, self.second)]
        self.assertEqual(len(provider.get_file_items([first, second])), 1)
        for selection in [[], [first], [first, FileInfo("file:///tmp/a.txt", "text/plain")],
                          [first, FileInfo("smb://server/a.pdf")],
                          [first, FileInfo("file:///tmp/folder.pdf", directory=True)]]:
            with self.subTest(selection=selection):
                self.assertFalse(provider.get_file_items(selection))

    def test_merge_preserves_originals_and_alphabetical_page_order(self):
        originals = [p.read_bytes() for p in (self.first, self.second)]
        output = self.folder / "resultado.pdf"
        self.module.merge_pdfs([self.second, self.first], output)
        text = subprocess.check_output(["pdftotext", str(output), "-"], text=True)
        self.assertLess(text.index("PRIMEIRO"), text.index("SEGUNDO"))
        self.assertEqual(text.count("\f"), 2)
        self.assertEqual([p.read_bytes() for p in (self.first, self.second)], originals)

    def test_refuses_existing_destination_and_source(self):
        output = self.folder / "resultado.pdf"
        output.write_bytes(b"nao substituir")
        for destination in [output, self.first]:
            original = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                self.module.merge_pdfs([self.first, self.second], destination)
            self.assertEqual(destination.read_bytes(), original)

    def test_invalid_pdf_leaves_no_output(self):
        self.second.write_text("PDF invalido")
        output = self.folder / "resultado.pdf"
        with self.assertRaises(ValueError):
            self.module.merge_pdfs([self.first, self.second], output)
        self.assertFalse(output.exists())
        self.assertEqual(len(list(self.folder.iterdir())), 2)

    def test_requires_two_files(self):
        with self.assertRaises(ValueError):
            self.module.merge_pdfs([self.first], self.folder / "resultado.pdf")

    def test_automatic_destination_preserves_existing_files(self):
        existing = self.folder / "01 orçamento $(teste)_join.pdf"
        existing.write_bytes(b"nao substituir")
        with patch.object(self.module, "show_message", side_effect=AssertionError("Diálogo inesperado")):
            self.module.main([str(self.second), str(self.first)])
        output = self.folder / "01 orçamento $(teste)_2_join.pdf"
        self.assertEqual(existing.read_bytes(), b"nao substituir")
        text = subprocess.check_output(["pdftotext", str(output), "-"], text=True)
        self.assertLess(text.index("PRIMEIRO"), text.index("SEGUNDO"))

    def test_menu_activation_runs_merge_in_separate_process(self):
        output = self.folder / "01 orçamento $(teste)_join.pdf"
        dialog = self.folder / "zenity"
        dialog.write_text('#!/bin/sh\nexit 1\n')
        dialog.chmod(0o755)
        provider = self.module.JuntarPdfsExtension()
        item = provider.get_file_items([FileInfo(p.as_uri()) for p in (self.first, self.second)])[0]
        launch = subprocess.Popen
        processes = []

        def capture_process(*args, **kwargs):
            process = launch(*args, **kwargs)
            processes.append(process)
            return process

        with patch.dict(os.environ, {"PATH": str(self.folder) + os.pathsep + os.environ["PATH"]}):
            with patch.object(self.module.subprocess, "Popen", side_effect=capture_process):
                item.emit("activate")
            self.assertEqual(len(processes), 1)
            self.assertEqual(processes[0].wait(timeout=10), 0)
        text = subprocess.check_output(["pdftotext", str(output), "-"], text=True)
        self.assertIn("PRIMEIRO", text)
        self.assertIn("SEGUNDO", text)


if __name__ == "__main__":
    unittest.main()
