# Histórico de versões

## Em desenvolvimento — 2026-10-21

- Posicionamento da roda próximo ao ponteiro, com conversão de coordenadas da janela para a área de arquivos e fallback central.

- Ampliação para 345 pares reais de mídia verificados, sem aliases ou cópias no mesmo formato.
- HEIC, BMP, GIF, ICO, JPEG 2000, JPEG XL, QOI, TGA, M4A, Opus, AIFF, WMA, AAC, MOV, MKV, AVI e WMV.
- Documentos/e-books com Pandoc, Office com LibreOffice, legendas com FFmpeg e compactados com libarchive.
- Círculo com seis destinos por página, botões centrais, roda do mouse e Page Up/Page Down.
- Exportação de todas as abas de planilhas e slides; imagens embutidas no HTML do Writer.
- Destinos de PDF baseados em texto identificados na interface, sem promessa de recuperar layout.

- Círculo de conversão acionado por Shift sozinho, sem arrastar os arquivos.
- Integração de Juntar PDFs ao círculo, preservando o menu e as regras anteriores.
- Conversões locais de imagens, áudio, vídeo e PDF com as ferramentas instaladas.
- Saídas exclusivas, sem sobrescrita, e exportação de todas as páginas dos PDFs.
- Instalação e remoção do módulo de conversão junto com a extensão.

## 0.1.0 — 2026-10-19

- Primeira publicação da extensão Nautilus PDF Join.
- Ação “Juntar PDFs…” para seleções com dois ou mais PDFs locais.
- União em ordem alfabética usando Poppler, em processo separado.
- Saída automática com final `_join.pdf`, sem diálogo de destino.
- Numeração de nomes existentes e preservação dos originais.
- Mensagens de erro, instalação e desinstalação por usuário.
- Oito testes automatizados e verificação manual do menu com PDFs de demonstração.
- Documentação em português, capturas reais e registro de continuidade.
