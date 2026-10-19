#!/bin/sh
set -eu

for dependency in python3 pdfunite zenity; do
    command -v "$dependency" >/dev/null 2>&1 || {
        printf 'Dependência ausente: %s. Consulte o README.\n' "$dependency" >&2
        exit 1
    }
done
python3 -c 'import gi; gi.require_version("Nautilus", "4.1")'

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
destination="${XDG_DATA_HOME:-$HOME/.local/share}/nautilus-python/extensions/juntar_pdfs.py"
install -Dm644 "$source_dir/juntar_pdfs.py" "$destination"
printf 'Instalado em %s\nReabra o Nautilus após encerrar suas operações de arquivos.\n' "$destination"
