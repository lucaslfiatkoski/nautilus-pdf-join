import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
