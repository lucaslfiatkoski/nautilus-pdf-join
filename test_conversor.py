import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from types import SimpleNamespace

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Nautilus', '4.1')
from gi.repository import Gio, GObject, Gtk, Nautilus


class DemoFile(GObject.Object, Nautilus.FileInfo):
    def __init__(self, path):
        super().__init__()
        self.path = path

    def do_get_location(self):
        return Gio.File.new_for_path(str(self.path))

    def do_is_directory(self):
        return False


class DemoItem(GObject.Object):
    file = GObject.Property(type=GObject.Object)


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('conversor.py')
        if not path.exists():
            raise AssertionError('O conversor do círculo ainda não existe')
        spec = importlib.util.spec_from_file_location('conversor', path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.image = self.folder / 'imagem $(teste).png'
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 24, 16)
        context = cairo.Context(surface)
        context.set_source_rgb(1, 0, 0)
        context.paint()
        surface.write_to_png(str(self.image))
        self.pdf = self.folder / '01 exemplo.pdf'
        surface = cairo.PDFSurface(str(self.pdf), 200, 100)
        context = cairo.Context(surface)
        context.move_to(10, 30)
        context.show_text('DEMONSTRACAO')
        context.show_page()
        surface.finish()

    def test_actions_respect_selection_type_and_multiple_pdfs(self):
        actions = lambda paths: {key for key, label in self.module.available_actions(paths)}
        self.assertIn('jpg', actions([self.image]))
        self.assertIn('pdf', actions([self.image]))
        self.assertNotIn('join', actions([self.pdf]))
        self.assertIn('join', actions([self.pdf, self.pdf]))
        self.assertIn('txt', actions([self.pdf]))
        self.assertFalse(actions([self.image, self.pdf]))
        self.assertFalse(actions([self.folder]))
        self.assertFalse(actions([]))

    def test_image_conversion_preserves_original_and_existing_output(self):
        original = self.image.read_bytes()
        existing = self.folder / 'imagem $(teste).jpg'
        existing.write_bytes(b'preservar')
        outputs = self.module.convert_files('jpg', [self.image])
        self.assertEqual(outputs, [self.folder / 'imagem $(teste)_2.jpg'])
        self.assertTrue(outputs[0].read_bytes().startswith(b'\xff\xd8'))
        self.assertEqual(existing.read_bytes(), b'preservar')
        self.assertEqual(self.image.read_bytes(), original)

    def test_pdf_text_and_all_pages_export(self):
        outputs = self.module.convert_files('txt', [self.pdf])
        self.assertIn('DEMONSTRACAO', outputs[0].read_text())
        images = self.module.convert_files('png', [self.pdf])
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0].read_bytes().startswith(b'\x89PNG'))

    def test_multipage_pdf_exports_every_page(self):
        surface = cairo.PDFSurface(str(self.pdf), 200, 100)
        context = cairo.Context(surface)
        for number in range(2):
            context.move_to(10, 30)
            context.show_text(f'PAGINA {number + 1}')
            context.show_page()
        surface.finish()
        outputs = self.module.convert_files('png', [self.pdf])
        self.assertEqual([p.name for p in outputs],
                         ['01 exemplo_pagina_1.png', '01 exemplo_pagina_2.png'])
        self.assertTrue(all(p.read_bytes().startswith(b'\x89PNG') for p in outputs))

    def test_detected_file_type_is_used_even_with_a_different_extension(self):
        renamed = self.pdf.with_suffix('.bin')
        self.pdf.rename(renamed)
        outputs = self.module.convert_files('txt', [renamed])
        self.assertIn('DEMONSTRACAO', outputs[0].read_text())

    def test_video_conversion(self):
        video = self.folder / 'exemplo.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=32x32:d=0.1', str(video)], check=True)
        outputs = self.module.convert_files('webm', [video])
        codec = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                         '-show_entries', 'stream=codec_name', '-of',
                                         'default=noprint_wrappers=1:nokey=1', str(outputs[0])], text=True)
        self.assertIn(codec.strip(), ('vp8', 'vp9', 'av1'))

    def test_many_image_frames_keep_their_original_order(self):
        frames = []
        for index in range(12):
            path = self.folder / f'frame{index:02d}.png'
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2, 2)
            context = cairo.Context(surface)
            context.set_source_rgb(index * 20 / 255, 0, 0)
            context.paint()
            surface.write_to_png(str(path))
            frames.append(path)
        animation = self.folder / 'animacao.gif'
        subprocess.run(['magick', *(str(p) for p in frames), str(animation)], check=True)
        outputs = self.module.convert_files('png', [animation])
        self.assertEqual(len(outputs), 12)
        for original, converted in zip(frames, outputs):
            expected = cairo.ImageSurface.create_from_png(str(original))
            actual = cairo.ImageSurface.create_from_png(str(converted))
            self.assertEqual(bytes(actual.get_data()), bytes(expected.get_data()))

    def test_expanded_image_and_audio_formats_are_available(self):
        image_actions = dict(self.module.available_actions([self.image]))
        for kind in ('heic', 'bmp', 'gif', 'ico', 'jp2', 'jxl', 'qoi', 'tga'):
            self.assertIn(kind, image_actions)
        audio = self.folder / 'audio.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=duration=0.1', str(audio)], check=True)
        for kind in ('m4a', 'opus', 'aiff', 'wma', 'aac'):
            self.assertIn(kind, dict(self.module.available_actions([audio])))
            result = self.module.convert_files(kind, [audio])[0]
            info = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                'stream=codec_type', '-of', 'default=noprint_wrappers=1:nokey=1', str(result)], text=True)
            self.assertIn('audio', info)

    def test_wheel_pages_include_every_format_and_wrap(self):
        actions = [(x, x.upper()) for x in ('png','jpg','webp','avif','bmp','heic','ico','tiff','pdf')]
        first, page, count = self.module.action_page(actions, 0)
        second, page2, count2 = self.module.action_page(actions, 1)
        self.assertEqual(first + second, actions)
        self.assertEqual((page, count, page2, count2), (0, 2, 1, 2))
        self.assertEqual(self.module.action_page(actions, 2)[0], first)
        self.assertEqual(self.module.action_page(actions, -1)[0], second)
        self.assertLessEqual(len(first), 6)

    def test_markdown_word_epub_and_pdf_text_exports(self):
        source = self.folder / 'anotacoes.md'
        source.write_text('# Documento\n\nConteudo sintetico de demonstracao.\n')
        for kind in ('docx', 'epub', 'odt', 'rtf', 'html', 'txt'):
            self.assertIn(kind, dict(self.module.available_actions([source])))
            output = self.module.convert_files(kind, [source])[0]
            self.assertGreater(output.stat().st_size, 0)
            if kind in ('docx','epub','odt'):
                self.assertTrue(zipfile.is_zipfile(output))
        output = self.module.convert_files('docx', [self.pdf])[0]
        with zipfile.ZipFile(output) as archive:
            self.assertIn(b'DEMONSTRACAO', archive.read('word/document.xml'))

    def test_missing_pandoc_hides_document_pipelines_that_need_it(self):
        source = self.folder / 'notas.md'
        source.write_text('# Exemplo\n\nDEMONSTRACAO\n')
        lookup = self.module.tool
        with patch.object(self.module,'tool',side_effect=lambda name: None if name == 'pandoc' else lookup(name)):
            self.assertFalse(self.module.available_actions([source]))
            with self.assertRaises(ValueError):
                self.module.convert_files('docx',[source])

    def test_worker_uses_the_discovered_executable_path(self):
        executable = self.folder / 'conversor-local'
        marker = self.folder / 'executado'
        executable.write_text('#!/bin/sh\nprintf ok > "$1"\n')
        executable.chmod(0o755)
        with patch.object(self.module,'tool',return_value=str(executable)):
            self.module._run(['conversor-local',str(marker)])
        self.assertEqual(marker.read_text(),'ok')

    def test_subtitle_conversion_preserves_timing_and_text(self):
        source = self.folder / 'legenda.srt'
        source.write_text('1\n00:00:01,000 --> 00:00:02,500\nTexto de demonstracao\n\n')
        output = self.module.convert_files('vtt', [source])[0]
        text = output.read_text()
        self.assertIn('WEBVTT', text)
        self.assertIn('00:01.000 --> 00:02.500', text)
        self.assertIn('Texto de demonstracao', text)
        output = self.module.convert_files('txt', [source])[0]
        self.assertIn('Texto de demonstracao', output.read_text())

    def test_archive_conversion_preserves_contents_without_extracting(self):
        source = self.folder / 'pacote.zip'
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('pasta/arquivo.txt','DADOS SINTETICOS')
        compressed = self.module.convert_files('tar.gz', [source])[0]
        zipped = self.module.convert_files('zip', [compressed])[0]
        with zipfile.ZipFile(zipped) as archive:
            self.assertEqual(archive.read('pasta/arquivo.txt'), b'DADOS SINTETICOS')
        self.assertFalse((self.folder/'pasta').exists())

    def test_archive_formats_and_single_gzip_file(self):
        import gzip
        source = self.folder / 'documento.txt.gz'
        with gzip.open(source, 'wb') as output:
            output.write(b'DADOS SINTETICOS')
        for kind in ('zip','tar','tar.gz','tar.bz2','tar.xz','7z'):
            output = self.module.convert_files(kind, [source])[0]
            result = subprocess.check_output(['bsdtar','-xOf',str(output),'./documento.txt'])
            self.assertEqual(result,b'DADOS SINTETICOS')

    def test_office_documents_to_pdf(self):
        if not self.module.tool('libreoffice'):
            self.skipTest('LibreOffice não instalado')
        source = self.folder / 'documento.md'
        source.write_text('# Titulo\n\nCONTEUDO SINTETICO.\n')
        docx = self.module.convert_files('docx', [source])[0]
        pdf = self.module.convert_files('pdf', [docx])[0]
        text = subprocess.check_output(['pdftotext',str(pdf),'-'],text=True)
        self.assertIn('CONTEUDO SINTETICO',text)

    def test_word_html_keeps_embedded_images_in_one_file(self):
        import base64
        if not self.module.tool('libreoffice'):
            self.skipTest('LibreOffice não instalado')
        source = self.folder / 'imagem.md'
        encoded = base64.b64encode(self.image.read_bytes()).decode()
        source.write_text(f'# Exemplo\n\n![Imagem](data:image/png;base64,{encoded})\n')
        docx = self.module.convert_files('docx', [source])[0]
        with zipfile.ZipFile(docx) as archive:
            self.assertTrue(any(name.startswith('word/media/') for name in archive.namelist()))
        outputs = self.module.convert_files('html', [docx])
        self.assertEqual(len(outputs),1)
        self.assertIn('data:image/', outputs[0].read_text())

    def test_spreadsheet_conversion_exports_every_sheet(self):
        if not self.module.tool('libreoffice'):
            self.skipTest('LibreOffice não instalado')
        source = self.folder / 'tabelas.fods'
        source.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.spreadsheet">
 <office:body><office:spreadsheet>
 <table:table table:name="Primeira"><table:table-row>
 <table:table-cell office:value-type="string"><text:p>ALFA</text:p></table:table-cell>
 </table:table-row></table:table>
 <table:table table:name="Segunda"><table:table-row>
 <table:table-cell office:value-type="string"><text:p>BETA</text:p></table:table-cell>
 </table:table-row></table:table>
 </office:spreadsheet></office:body></office:document>''')
        xlsx = self.module.convert_files('xlsx', [source])[0]
        self.assertTrue(zipfile.is_zipfile(xlsx))
        outputs = self.module.convert_files('csv',[xlsx])
        self.assertEqual(len(outputs),2)
        self.assertTrue(any('ALFA' in p.read_text() for p in outputs))
        self.assertTrue(any('BETA' in p.read_text() for p in outputs))

    def test_presentations_export_all_slides(self):
        if not self.module.tool('libreoffice'):
            self.skipTest('LibreOffice não instalado')
        source = self.folder / 'slides.md'
        source.write_text('# PRIMEIRO\n\nUM\n\n# SEGUNDO\n\nDOIS\n')
        slides = self.folder / 'slides.pptx'
        subprocess.run([self.module.tool('pandoc'),'--sandbox','-f','markdown','-t','pptx',
                        '-o',str(slides),str(source)],check=True,capture_output=True)
        outputs = self.module.convert_files('png',[slides])
        self.assertEqual(len(outputs),2)

    def test_failure_leaves_no_output_and_rejects_unsupported_conversion(self):
        invalid = self.folder / 'quebrada.png'
        invalid.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
        before = set(self.folder.iterdir())
        with self.assertRaises(ValueError):
            self.module.convert_files('jpg', [invalid])
        self.assertEqual(set(self.folder.iterdir()), before)
        with self.assertRaises(ValueError):
            self.module.convert_files('mp3', [self.image])
        with self.assertRaises(ValueError):
            self.module.convert_files('jpg', [])

    def test_image_pdf_and_audio_conversion(self):
        outputs = self.module.convert_files('pdf', [self.image])
        info = subprocess.check_output(['pdfinfo', str(outputs[0])], text=True)
        self.assertIn('Pages:', info)
        audio = self.folder / 'tom.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.1', str(audio)], check=True)
        outputs = self.module.convert_files('mp3', [audio])
        self.assertGreater(outputs[0].stat().st_size, 0)

    def test_selection_reads_grid_and_tree_rows_without_using_clipboard(self):
        store = Gio.ListStore.new(DemoItem)
        for path in (self.image, self.pdf):
            store.append(DemoItem(file=DemoFile(path)))
        selection = Gtk.MultiSelection.new(store)
        selection.select_item(1, False)
        self.assertEqual(self.module.selection_paths(selection), [str(self.pdf)])
        tree = Gtk.TreeListModel.new(store, False, False, lambda item: None)
        selection = Gtk.MultiSelection.new(tree)
        selection.select_all()
        self.assertEqual(self.module.selection_paths(selection), [str(self.image), str(self.pdf)])

    def test_shift_alone_opens_but_selection_shortcuts_do_not(self):
        gesture = self.module.ShiftGesture()
        gesture.press('Shift_L', False)
        self.assertTrue(gesture.release('Shift_L'))
        self.assertFalse(gesture.release('Shift_L'))
        for cancel in ('Right', 'a', 'pointer'):
            gesture.press('Shift_R', False)
            gesture.press(cancel, False)
            self.assertFalse(gesture.release('Shift_R'))
        gesture.press('Shift_L', True)
        self.assertFalse(gesture.release('Shift_L'))

    def test_wheel_hit_testing_excludes_center_and_outside(self):
        hit = self.module.sector_at
        self.assertEqual(hit(160, 40, 4), 0)
        self.assertEqual(hit(280, 160, 4), 1)
        self.assertEqual(hit(160, 280, 4), 2)
        self.assertEqual(hit(40, 160, 4), 3)
        self.assertIsNone(hit(160, 160, 4))
        self.assertIsNone(hit(0, 0, 4))
        self.assertIsNone(hit(160, 40, 0))

    def test_wheel_anchor_uses_pointer_in_parent_coordinates(self):
        surface = object()
        pointer = SimpleNamespace(get_surface_at_position=lambda: (surface,100.0,120.0))
        seat = SimpleNamespace(get_pointer=lambda: pointer)
        display = SimpleNamespace(get_default_seat=lambda: seat)
        native = SimpleNamespace(get_surface=lambda: surface, get_surface_transform=lambda: (2.0,3.0),
                                 compute_point=lambda parent,p: (True,SimpleNamespace(x=p.x-30,y=p.y-40)))
        parent = SimpleNamespace(get_native=lambda: native, get_display=lambda: display,
                                 get_width=lambda: 800, get_height=lambda: 600)
        point = self.module.pointer_anchor(parent)
        self.assertEqual((point.x,point.y),(72,83))
        pointer.get_surface_at_position = lambda: (None,0,0)
        point = self.module.pointer_anchor(parent)
        self.assertEqual((point.x,point.y),(400,300))


if __name__ == '__main__':
    unittest.main()
