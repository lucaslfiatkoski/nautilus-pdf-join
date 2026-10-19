#!/bin/sh
set -eu

destination="${XDG_DATA_HOME:-$HOME/.local/share}/nautilus-python/extensions/juntar_pdfs.py"
rm -f -- "$destination"
printf 'Extensão removida de %s\nReabra o Nautilus para atualizar o menu.\n' "$destination"
