"""Ação do Nautilus para juntar PDFs locais sem substituir arquivos."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import gi

gi.require_version("Nautilus", "4.1")
from gi.repository import GObject, Nautilus


def merge_pdfs(paths, destination):
    paths = sorted((Path(p).absolute() for p in paths), key=lambda p: (p.name.casefold(), str(p)))
    destination = Path(destination).absolute()
    if len(paths) < 2 or any(not p.is_file() for p in paths):
        raise ValueError("Selecione pelo menos dois arquivos PDF locais.")
    if os.path.lexists(destination):
        raise FileExistsError("Já existe um arquivo com esse nome. Escolha outro nome.")

    with tempfile.TemporaryDirectory(prefix=".juntar-pdfs-", dir=destination.parent) as temp:
        merged = Path(temp) / "unidos.pdf"
        result = subprocess.run(
            ["pdfunite", *(str(p) for p in paths), str(merged)],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise ValueError("Não foi possível juntar os PDFs. Verifique se estão válidos e sem senha.\n\n"
                             + result.stderr.strip()[:1500])
        # A criação exclusiva protege também contra arquivos criados durante a conversão.
        with destination.open("xb") as output:
            try:
                with merged.open("rb") as source:
                    shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            except BaseException:
                destination.unlink()
                raise


def show_message(kind, text):
    subprocess.run(["zenity", kind, "--no-markup", "--title=Juntar PDFs", "--text=" + text])


def main(paths):
    if len(paths) < 2:
        show_message("--error", "Selecione pelo menos dois PDFs.")
        return
    first = min((Path(p).absolute() for p in paths), key=lambda p: (p.name.casefold(), str(p)))
    number = 1
    while True:
        suffix = "" if number == 1 else f"_{number}"
        destination = first.with_name(f"{first.stem}{suffix}_join.pdf")
        try:
            merge_pdfs(paths, destination)
        except FileExistsError:
            number += 1
            continue
        except (OSError, ValueError) as error:
            show_message("--error", str(error))
        return


class JuntarPdfsExtension(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files):
        if len(files) < 2:
            return []
        paths = []
        for file in files:
            path = file.get_location().get_path()
            if not path or file.is_directory() or not file.is_mime_type("application/pdf"):
                return []
            paths.append(path)
        item = Nautilus.MenuItem(
            name="JuntarPdfs::merge", label="Juntar PDFs…",
            tip="Unir os PDFs em ordem alfabética, preservando os originais",
        )
        item.connect("activate", self.activate, paths)
        return [item]

    def activate(self, item, paths):
        try:
            subprocess.Popen(["/usr/bin/python3", str(Path(__file__).resolve()), *paths])
        except OSError as error:
            show_message("--error", str(error))


if __name__ == "__main__":
    main(sys.argv[1:])
