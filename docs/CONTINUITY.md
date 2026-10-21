# Continuidade do projeto

## Recorte visual — 2026-10-21

O usuário aprovou adicionar Recortar na roda para uma imagem/PDF, com janela pequena, prévia e seleção arrastável, salvando cópia. O módulo `recortar.py` abre um processo GTK separado, com controles percentuais acessíveis, restaurar área, navegação de páginas e opção de aplicar a todas. Imagens saem em PNG (primeiro quadro, orientação automática). PDFs saem em PDF por Poppler/Cairo, com clipping proporcional por página; preservam a aparência, mas não links, formulários ou assinaturas, e não devem ser usados para apagar dados sigilosos. Os limites aparecem na janela e no README. A opção fica na primeira página para seleção única; seleções múltiplas e Juntar PDFs mantêm o fluxo anterior.

O recorte reutiliza `_publish`, preservando originais e arquivos existentes. Campos e navegação são bloqueados durante o processamento; carregamento e gravação usam tarefas fora do laço GTK. Dependências já presentes: ImageMagick, Cairo e Poppler GI. Nenhuma dependência foi instalada. Instalação/remoção e testes foram ampliados para o novo módulo. Testes usam apenas arquivos sintéticos.

Verificação: `RUN_WHEEL_UI=1 python3 -m unittest -v` executou 42 testes: 41 passaram e a matriz opcional de mídia foi pulada. Teste de instalação repetido após incluir a verificação de Pycairo; compilação, `sh -n` e `git diff --check` passaram. Revisão independente não encontrou defeitos funcionais ou de preservação de arquivos. Capturas reais atualizadas em `docs/images/`. `./install.sh` sincronizou os três módulos, comparados byte a byte; backup anterior em `~/.local/share/nautilus-pdf-join/backups/antes-do-recorte-2026-10-21/`. Nautilus reaberto e a janela instalada foi confirmada visível e flutuante no Niri, com PDF sintético de duas páginas. Logs tiveram avisos do ambiente gráfico/Vulkan, sem traceback da extensão ou da janela. Nenhum documento particular foi usado.

## Novo repositório — 2026-10-21

O usuário autorizou criar um repositório público na conta conectada após o envio ao projeto original retornar HTTP 403. O novo destino é `https://github.com/lucaslfiatkoski/nautilus-pdf-join`, com a versão atual na branch `main`. O remoto original foi preservado como `upstream`; `origin` aponta para o novo repositório. O histórico e a licença foram preservados, e o comando de instalação do README aponta para a nova cópia. Nenhum comportamento do código mudou nesta publicação.

## Ordem dos destinos — 2026-10-21

O usuário pediu as opções mais utilizadas primeiro. Foram priorizados formatos comuns por categoria, sem coletar frequência de uso: imagens JPG/PNG/PDF; PDFs DOCX/JPG/PNG/texto, com Juntar PDFs primeiro nas seleções múltiplas; documentos PDF/DOCX/TXT; planilhas XLSX/PDF/CSV; vídeos MP4/MP3/GIF; compactados ZIP/7Z/TAR.GZ. Os outros destinos continuam nas páginas seguintes. A mudança é de ordenação, sem alterar os pipelines de conversão.

## Posição da roda — 2026-10-21

O usuário solicitou que a roda abrisse perto do ponteiro, com captura da roda distante do arquivo selecionado. `pointer_anchor` lê a posição atual pelo GDK, confere se a superfície pertence à janela e usa a transformação da superfície e `Gtk.Widget.compute_point` para obter coordenadas na área de arquivos. O popover é deslocado em metade do diâmetro para aproximar o centro do cursor. Sem posição válida na janela, usa o centro da área de arquivos. Teste de regressão cobre deslocamento de coordenadas e fallback. As pastas abertas são registradas só para restaurar a navegação após atualizar o Nautilus, sem ler documentos.

## Ampliação das conversões — 2026-10-21

Após a primeira instalação, o usuário pediu a variedade do Tangerine original, com mais de 200 conversões. A ampliação mantém o gesto seleciona + Shift sozinho, sem arrastar, e o círculo agora tem páginas de seis destinos. Troca de página por ‹/› no centro, roda do mouse ou Page Up/Page Down.

Implementados novos formatos de imagem/áudio/vídeo e pipelines de documentos, e-books, planilhas, slides, legendas e compactados. A matriz opcional executou **345 pares reais de mídia** (183 imagem, 72 áudio, 90 vídeo), convertendo e reabrindo cada resultado. O arquivo `docs/conversoes-verificadas.json` registra os pares; os testes adicionais cobrem as demais famílias.

Pandoc 3.12.1 e LibreOffice 26.8.1 foram instalados por usuário em `~/.local/opt/`, com links `~/.local/bin/pandoc` e `~/.local/bin/libreoffice`. Downloads oficiais tiveram SHA-256 verificado e origem registrada em `SOURCE.txt`. A tentativa de instalar LibreOffice pelo pacman falhou em espelhos/assinaturas e não alterou pacotes; não foram desativadas verificações. Não é necessário instalar os 269 pacotes de dependências Haskell do pandoc-cli para usar o binário oficial estático.

Limites mantidos explícitos: PDF para documentos é extração de texto, sem reconstrução do layout nem OCR; não há exportação para Apple Pages. Perfis do LibreOffice são isolados, com macros bloqueadas; o perfil pessoal não é usado. Arquivos e nomes existentes continuam preservados.

A revisão independente identificou uma opção de documento que podia depender de Pandoc ausente. Foi corrigida com filtragem do pipeline e erro legível; teste de regressão adicionado. O teste visual GTK usa um popover real sem grab modal para não depender de serial físico Wayland; a navegação pelas três páginas foi validada.

Verificação final: `RUN_WHEEL_UI=1 python3 -m unittest -v` executou 34 testes: 33 passaram e a matriz opcional foi marcada como pulada nessa execução, pois já havia passado separadamente com os 345 pares. Compilação Python, scripts de instalação e `git diff --check` também passaram. `./install.sh` sincronizou os dois arquivos e as cópias foram comparadas byte a byte. O Nautilus normal foi reaberto na pasta de demonstração. A versão instalada anterior está em `~/.local/share/nautilus-pdf-join/backups/antes-de-ampliar-conversoes-2026-10-21/`. Não houve publicação no GitHub.

## Atualização — 2026-10-21: círculo de conversão

O usuário pediu a interação do Tangerine no Nautilus, integrada à união de PDFs. Corrigiu o gesto: **selecionar arquivos e apertar Shift, sem arrastar**. Aprovou a implementação do círculo com opções conforme a seleção e preservação dos originais.

Trabalho na branch `feat/circulo-shift`, em `/home/lucas/nautilus-pdf-join`. `conversor.py` contém a interface GTK4 e as conversões locais; a extensão existente carrega o módulo uma vez. Instalação e desinstalação agora tratam os dois arquivos. Não foi instalado o Tangerine original, exclusivo de macOS, nem o produto independente Open Tangerine.

Conversões implementadas: imagens para PNG/JPG/WebP/AVIF/TIFF/PDF, PDF para texto/PNG/JPG, áudio para MP3/WAV/FLAC/OGG e vídeo para MP4/WebM ou áudio. A união usa o processo existente e mantém `_join.pdf`, ordenação e proteção de nomes. Office/OCR e ferramentas de edição não foram implementados.

Ambiente desta sessão: CachyOS, Niri 26.04, Nautilus 50.3.1, nautilus-python 4.2.0, GTK4 4.22.5. A interface foi exercitada numa instância isolada do Nautilus, em sessão D-Bus própria, com PDFs sintéticos em `/tmp/pdf-join-wheel-check`. A roda foi renderizada e houve produção de PDF unido e PNG pela interface. Os testes automatizados cobrem conversões reais, colisões, entradas inválidas, páginas múltiplas, seleção em grade/árvore, setores e Shift sozinho versus combinações.

O atalho depende do modelo interno do Nautilus. Não capturamos teclas globalmente nem modificamos a configuração do Niri. É uma implementação inicial da interação, sem equivalência de todos os formatos ou funcionalidades do Tangerine.

Entrega local concluída: 20 testes passaram, `sh -n`, compilação Python e `git diff --check` passaram. A verificação da instância real confirmou círculo visível, seleção de dois PDFs, união com duas páginas e ordem correta. Uma revisão independente encontrou a ordenação lexicográfica de quadros de imagens; foi corrigida com nomes temporários de sequência preenchidos com zeros e um teste de regressão de 12 quadros.

`./install.sh` foi executado e os dois arquivos instalados foram comparados com o projeto. A versão anterior de `juntar_pdfs.py` está guardada em `~/.local/share/nautilus-pdf-join/backups/antes-do-circulo-2026-10-21/`. A instância isolada de testes foi encerrada e a pasta de demonstração reaberta no Nautilus normal. Nada foi publicado no GitHub nesta etapa. A interface completa foi exercitada em grade; o modelo de seleção em árvore foi testado automaticamente. Não houve teste exaustivo de codecs ou sistemas de arquivos sem hard links.

Registro da primeira publicação, em 19 de outubro de 2026. Leia este arquivo junto com o README antes de retomar o trabalho.

## Objetivo e decisões do usuário

O objetivo é selecionar mais de um PDF no gerenciador de arquivos e ter uma opção de união diretamente no menu do botão direito.

O gerenciador identificado foi o Nautilus, usado em um ambiente CachyOS com Niri e Noctalia. A implementação é uma extensão do Nautilus; não é necessário modificar o Noctalia.

A primeira implementação abria um diálogo para salvar. O usuário pediu explicitamente a remoção desse diálogo e a criação automática de um arquivo com final `join`. A regra atual é `<primeiro_nome>_join.pdf`, com numeração antes de `_join` quando necessário. A ordem alfabética foi adotada e informada durante a implementação.

Depois, o usuário solicitou a criação de um repositório público, um README detalhado com captura do menu e documentação para continuar o projeto em outra sessão.

## Repositório e arquivos locais

- Nome público: `pir0c0pter0/nautilus-pdf-join`.
- URL: <https://github.com/pir0c0pter0/nautilus-pdf-join>.
- Branch principal: `main`.
- Primeira versão publicada: [`v0.1.0`](https://github.com/pir0c0pter0/nautilus-pdf-join/releases/tag/v0.1.0), commit `04cd6f3`.
- Visibilidade confirmada no GitHub: pública. A release está publicada, sem marcação de rascunho.
- Licença adotada: MIT.
- Pasta de trabalho original: `$HOME/Projetos/gerenciador_noctalia`.
- Cópia instalada: `${XDG_DATA_HOME:-$HOME/.local/share}/nautilus-python/extensions/juntar_pdfs.py`.

O código da pasta de trabalho e a cópia instalada são arquivos separados. Use `./install.sh` após editar a extensão. Não presuma que editar o repositório atualiza automaticamente o arquivo carregado pelo Nautilus.

## O que já foi implementado

- Menu condicional para pelo menos dois PDFs locais.
- Execução da união em processo separado com `pdfunite`.
- Criação automática na pasta do primeiro nome em ordem alfabética.
- Proteção dos originais e dos nomes de saída já existentes.
- Numeração de colisões: `_2_join.pdf`, `_3_join.pdf` etc.
- Mensagens gráficas de erro com Zenity.
- Scripts de instalação e desinstalação para o usuário atual.
- Testes automatizados de PDFs, ativação do menu e instalação.
- README com capturas reais do menu e do resultado.
- Guia de desenvolvimento e histórico de versões.

## Validação da primeira publicação

A suíte tem oito testes: sete do comportamento da extensão e um da instalação. Os testes geram PDFs temporários com textos identificáveis; verificam ordem e presença das páginas, nomes automáticos, preservação de arquivos, rejeição de PDFs inválidos, visibilidade do menu, execução em processo separado e instalação/desinstalação repetidas.

O menu foi aberto em uma janela real do Nautilus com `01 Introducao.pdf` e `02 Detalhes.pdf`. A ação foi executada pelo menu e criou `01 Introducao_join.pdf`, sem diálogo de destino. `pdfinfo` confirmou duas páginas e `pdftotext` confirmou a ordem dos textos. As imagens usadas no README vieram dessa demonstração.

Ambiente verificado: Nautilus 51.1, nautilus-python 4.2.0, Python 3.14.8, PyGObject 3.58.1, Poppler 26.08.0, Zenity 4.2.2 e Pycairo 1.29.2. A verificação manual dessa sessão usou dois PDFs simples; não valida todas as combinações de PDFs reais.

## Como retomar

1. Abra a pasta do projeto e leia `README.md`, este registro e `docs/DEVELOPMENT.md`.
2. Confira o estado com `git status`, `git log -5 --oneline` e `git remote -v`.
3. Rode `python3 -m unittest -v` antes e depois de mudar o comportamento.
4. Faça a menor alteração necessária ao pedido atual, preservando as decisões acima.
5. Atualize `CHANGELOG.md` e este registro quando mudar o comportamento ou o estado da distribuição.
6. Reinstale com `./install.sh` e teste com PDFs de demonstração.

## Possíveis próximos passos, ainda não implementados

- Testar e, se necessário, adaptar a API 4.0 para outras distribuições.
- Configurar testes contínuos no GitHub Actions.
- Preparar um pacote para Arch/AUR se houver demanda.
- Avaliar progresso/cancelamento para PDFs grandes.
- Testar documentos com assinaturas, formulários, marcadores e outros recursos especiais.
- Avaliar publicação atômica do resultado e comportamento após interrupções.

Nenhum desses itens altera o escopo da versão inicial. Não prometer suporte a versões ou recursos sem testar.
