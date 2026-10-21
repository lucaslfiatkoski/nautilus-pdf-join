# Desenvolvimento

## Estrutura

```text
juntar_pdfs.py              Extensão e processo de união
conversor.py                Círculo GTK, atalho e processo de conversão
test_conversor.py           Seleção, gesto, setores e conversões sintéticas
install.sh                 Instalação para o usuário atual
uninstall.sh               Remoção da extensão do usuário atual
test_juntar_pdfs.py         Testes do comportamento e da integração
test_install.py            Teste dos scripts de instalação
README.md                  Instalação, uso e solução de problemas
CHANGELOG.md               Histórico de versões
docs/CONTINUITY.md          Registro para retomar o trabalho
docs/images/               Capturas reais usadas no README
```

## Fluxo de execução

1. `nautilus-python` carrega `juntar_pdfs.py` no processo do Nautilus.
2. `JuntarPdfsExtension.get_file_items()` recebe os itens selecionados e valida quantidade, MIME, tipo e caminho local.
3. O menu conecta o sinal `activate` a `JuntarPdfsExtension.activate()`.
4. `activate()` inicia `/usr/bin/python3` com o caminho da extensão e os caminhos dos PDFs como argumentos separados.
5. `main()` determina o primeiro nome em ordem alfabética e tenta criar `<nome>_join.pdf`.
6. `merge_pdfs()` valida as entradas, ordena os PDFs, executa `pdfunite` em um diretório temporário e copia o resultado para um arquivo aberto com `xb`.
7. `FileExistsError` faz `main()` tentar `<nome>_2_join.pdf`, `<nome>_3_join.pdf` e assim por diante. Outros erros de arquivo ou de conversão são mostrados pelo Zenity.

`merge_pdfs()` é a função compartilhada pela interface e pelos testes. Ela recebe um destino explícito e não decide o nome automático. O nome e as tentativas em caso de colisão pertencem a `main()`.

## Decisões que devem ser preservadas

- A operação normal não abre diálogo de destino nem confirmação de sucesso.
- O nome deve terminar em `_join.pdf`, inclusive nas repetições: `_2_join.pdf`.
- A ordem é determinada por `(nome.casefold(), caminho completo)`, não pela ordem da seleção.
- Originais e destinos já existentes não podem ser substituídos.
- Não usar `shell=True` nem concatenar caminhos em comandos de shell.
- Não executar a conversão dentro do callback do Nautilus.
- Usar `/usr/bin/python3` para o processo auxiliar: o interpretador embutido do Nautilus não deve determinar o executável por `sys.executable`.
- Os scripts de instalação respeitam `XDG_DATA_HOME` e não precisam de privilégios administrativos.
- Não adicionar processamento pela rede ou dependências de Python para PDF enquanto `pdfunite` resolver o caso de uso.

## Verificação antes de publicar uma mudança

```bash
python3 -m unittest -v
python3 -m py_compile juntar_pdfs.py conversor.py test_conversor.py test_juntar_pdfs.py test_install.py
sh -n install.sh uninstall.sh
git diff --check
```

O teste de instalação copia a extensão para um diretório temporário, repete a instalação, remove a extensão duas vezes e confirma que outra extensão no mesmo diretório continua intacta. Nenhum teste instala pacotes do sistema.

Para verificar a interface, crie dois PDFs de demonstração com conteúdo identificável, instale a versão modificada e reabra o Nautilus quando não houver operações de arquivos em andamento. Confira:

1. Um PDF: opção ausente.
2. Dois PDFs locais: opção presente.
3. PDF mais outro tipo de arquivo: opção ausente.
4. União pelo menu: resultado aparece sem diálogo de destino.
5. Segunda união dos mesmos originais: novo nome numerado, sem substituir o primeiro resultado.
6. `pdfinfo` confirma a quantidade de páginas; `pdftotext` confirma a ordem dos textos de demonstração.

## Limites técnicos conhecidos

- O círculo instala `Gtk.EventControllerKey` somente nas janelas `NautilusWindow`. Lê a seleção da grade ou lista com foco, incluindo linhas `Gtk.TreeListRow`, pelo campo interno `NautilusViewItem:file`. Essa parte não é um contrato público de extensões e precisa de verificação após atualizar o Nautilus.
- Shift sozinho abre ao soltar; outra tecla ou um clique cancela o gesto. Campos editáveis e combinações com modificadores não abrem o círculo. A roda usa `Gtk.Popover`, botões acessíveis e desenho Cairo, sem captura global de teclado ou alteração do Niri.
- O processo `conversor.py --convert FORMATO CAMINHOS...` executa ImageMagick, FFmpeg ou Poppler fora do Nautilus. Publica cada saída usando link exclusivo de um temporário na mesma pasta; exige suporte a hard links no sistema de arquivos de destino. Não há fallback inseguro para sobrescrever.
- As conversões não são um sandbox de arquivos: os limites e suporte dos formatos são os das ferramentas instaladas. O limite de três minutos vale por chamada; lotes e PDFs com muitas páginas podem levar mais tempo no total. Cancelar/fechar o círculo não interrompe conversões já iniciadas.

- A API exigida é Nautilus 4.1. Não há fallback para 4.0.
- A mensagem de erro é gráfica; executar o arquivo diretamente como comando não é uma CLI com contrato de códigos de saída. Erros tratados por `main()` não garantem status de saída diferente de zero.
- A publicação do resultado usa cópia exclusiva, não renomeação atômica. Um leitor pode observar o arquivo durante a cópia; interrupções abruptas podem deixar saída parcial.
- O arquivo final usa as permissões padrão de criação do processo, afetadas pela `umask`; permissões e ACLs dos originais não são copiadas.
- O processo usa o `pdfunite` e o `zenity` encontrados no `PATH`.
- O instalador verifica a API introspectável, mas não consegue garantir apenas com essa verificação que o carregador `nautilus-python` foi instalado corretamente.
- Não há progresso, cancelamento, seleção de páginas, ordenação manual ou entrada de senha.
- Atualizações do Nautilus, Python ou Poppler podem exigir novos testes.

Esses limites estão documentados para orientar futuras mudanças. Não constituem uma lista de funcionalidades prometidas.

## Capturas de tela

`docs/images/menu-juntar-pdfs.png` mostra dois PDFs selecionados e o item de menu destacado. `docs/images/resultado-join.png` mostra os originais e o arquivo criado.

As imagens foram capturadas da janela real do Nautilus usando o recurso de captura de janela do Niri. Os PDFs eram sintéticos, em uma pasta temporária chamada `nautilus-pdf-join-demo`. Não publique capturas de documentos particulares, outras janelas ou dados de autenticação. Ao alterar o comportamento ou o texto da interface, atualize as capturas correspondentes.

## Referências

- [Carregamento de extensões Python no Nautilus](https://gnome.pages.gitlab.gnome.org/nautilus-python/nautilus-python-overview.html).
- [API Nautilus 4.1](https://gnome.pages.gitlab.gnome.org/nautilus/).
- `man pdfunite`: comportamento da versão de Poppler instalada.
