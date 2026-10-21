"""Recortes reais com arquivos sintéticos, sem documentos pessoais."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cairo
import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler


class CropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        path = Path(__file__).with_name('recortar.py')
        if path.exists():
            spec = importlib.util.spec_from_file_location('recortar', path)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertIsNotNone(self.module, 'O recorte visual ainda não foi implementado')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.image = self.folder / 'imagem $(teste).png'
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(1, 0, 0)
        ctx.paint()
        ctx.set_source_rgb(0, 0, 1)
        ctx.rectangle(50, 25, 100, 50)
        ctx.fill()
        surface.write_to_png(str(self.image))
        self.pdf = self.folder / 'duas paginas.pdf'
        surface = cairo.PDFSurface(str(self.pdf), 200, 100)
        ctx = cairo.Context(surface)
        for width, height in ((200, 100), (400, 200)):
            surface.set_size(width, height)
            ctx.set_source_rgb(0, 0, 1)
            ctx.rectangle(width / 4, height / 4, width / 2, height / 2)
            ctx.fill()
            ctx.show_page()
        surface.finish()

    def test_image_crop_pixels_and_exclusive_output(self):
        original = self.image.read_bytes()
        document = self.module.CropDocument(self.image)
        self.assertEqual(document.count, 1)
        output = document.save((.25, .25, .5, .5), 0, False)
        self.assertEqual(output.name, 'imagem $(teste)_recorte.png')
        cropped = cairo.ImageSurface.create_from_png(str(output))
        self.assertEqual((cropped.get_width(), cropped.get_height()), (100, 50))
        self.assertEqual(bytes(cropped.get_data())[:4], b'\xff\x00\x00\xff')
        again = document.save((.25, .25, .5, .5), 0, False)
        self.assertEqual(again.name, 'imagem $(teste)_recorte_2.png')
        self.assertEqual(output.read_bytes(), again.read_bytes())
        self.assertEqual(self.image.read_bytes(), original)

    def test_pdf_current_page_keeps_other_page_and_all_uses_relative_area(self):
        original = self.pdf.read_bytes()
        document = self.module.CropDocument(self.pdf)
        self.assertEqual(document.count, 2)
        output = document.save((.25, .25, .5, .5), 1, False)
        pdf = Poppler.Document.new_from_file(output.as_uri(), None)
        self.assertEqual(pdf.get_n_pages(), 2)
        self.assertEqual(pdf.get_page(0).get_size(), (200, 100))
        self.assertEqual(pdf.get_page(1).get_size(), (200, 100))
        all_output = document.save((.25, .25, .5, .5), 0, True)
        pdf = Poppler.Document.new_from_file(all_output.as_uri(), None)
        self.assertEqual(pdf.get_page(0).get_size(), (100, 50))
        self.assertEqual(pdf.get_page(1).get_size(), (200, 100))
        # Reabre e renderiza o recorte: o centro azul deve preencher a nova página.
        preview = self.module.CropDocument(all_output).preview(0)
        self.assertEqual(bytes(preview.get_data())[:4], b'\xff\x00\x00\xff')
        self.assertEqual(self.pdf.read_bytes(), original)

    def test_rectangle_validation_and_preview_coordinates(self):
        for rect in ((0, 0, 0, 1), (-.1, 0, .5, 1), (0, 0, 2, 1),
                     (0, float('nan'), 1, 1), (0, 0, 1, float('inf'))):
            with self.assertRaises(ValueError):
                self.module.CropDocument(self.image).save(rect, 0, False)
        self.assertFalse(list(self.folder.glob('*recorte*')))
        self.assertEqual(self.module.fit_rect(200, 100, 600, 400), (0, 50, 600, 300))
        self.assertEqual(self.module.drag_rect((.8, .9), (-.1, .2)), (0, .2, .8, .7))

    def test_zoom_preview_has_more_detail_without_changing_pdf_crop(self):
        document = self.module.CropDocument(self.pdf)
        normal = document.preview(0)
        enlarged = document.preview(0, 3)
        self.assertGreater(enlarged.get_width(), normal.get_width())
        self.assertGreater(enlarged.get_height(), normal.get_height())
        output = document.save((.25, .25, .5, .5), 0, False)
        cropped = self.module.CropDocument(output)
        self.assertEqual(cropped.size(0), (100, 50))

    def test_crop_available_only_for_single_image_or_pdf_and_not_as_conversion(self):
        import conversor
        for path in (self.image, self.pdf):
            actions = conversor.available_actions([path])
            self.assertIn(('crop', 'Recortar'), actions[:6])
            with self.assertRaises(ValueError):
                conversor.convert_files('crop', [path])
        self.assertNotIn('crop', dict(conversor.available_actions([self.pdf, self.pdf])))

    def test_invalid_input_and_page_leave_no_output(self):
        bad = self.folder / 'invalido.pdf'
        bad.write_text('arquivo inválido')
        with self.assertRaises(Exception):
            self.module.CropDocument(bad)
        document = self.module.CropDocument(self.pdf)
        for page in (-1, 2):
            with self.assertRaises(ValueError):
                document.save((0, 0, 1, 1), page, False)
        self.assertFalse(list(self.folder.glob('*recorte*')))

    @unittest.skipUnless(shutil.which('qpdf'), 'Requer qpdf para preparar rotação sintética.')
    def test_rotated_pdf_uses_visible_coordinates(self):
        rotated = self.folder / 'girado.pdf'
        subprocess.run(['qpdf', str(self.pdf), '--rotate=+90:1-z', str(rotated)],
                       check=True, capture_output=True)
        document = self.module.CropDocument(rotated)
        self.assertEqual(document.size(0), (100, 200))
        output = document.save((.25, .25, .5, .5), 0, True)
        result = self.module.CropDocument(output)
        self.assertEqual(result.size(0), (50, 100))
        self.assertEqual(bytes(result.preview(0).get_data())[:4], b'\xff\x00\x00\xff')

    @unittest.skipUnless(os.environ.get('RUN_WHEEL_UI') == '1', 'Requer sessão gráfica.')
    def test_real_window_drag_pages_and_save(self):
        from gi.repository import Gtk, GLib
        Gtk.init()
        app = Gtk.Application(application_id='br.local.RecorteTeste')
        app.register(None)
        window = self.module.CropWindow(app, self.pdf)
        window.present()
        context = GLib.MainContext.default()
        import time
        def until(predicate):
            deadline = time.monotonic() + 15
            while not predicate() and time.monotonic() < deadline:
                while context.pending():
                    context.iteration(False)
                time.sleep(.01)
            self.assertTrue(predicate())
        try:
            until(lambda: window.document is not None and not window.busy)
            self.assertTrue(window.get_mapped())
            self.assertGreater(window.canvas.get_width(), 0)
            x, y, w, h = self.module.fit_rect(200, 100, window.canvas.get_width(), window.canvas.get_height())
            window.drag.emit('drag-begin', x + w / 4, y + h / 4)
            window.drag.emit('drag-update', w / 2, h / 2)
            window.drag.emit('drag-end', w / 2, h / 2)
            for actual, expected in zip(window.rectangle(), (.25, .25, .5, .5)):
                self.assertAlmostEqual(actual, expected, places=2)
            selected = window.rectangle()
            for _ in range(4):
                window.zoom_in.emit('clicked')
                until(lambda: not window.busy and not window.zoom_layout_pending)
                until(lambda: window.canvas.get_width() >= window.canvas.get_content_width())
            until(lambda: window.canvas.get_width() > window.scroller.get_width())
            self.assertGreater(window.zoom, 2)
            self.assertEqual(window.rectangle(), selected)
            # Ao rolar, o gesto continua em coordenadas locais do canvas ampliado.
            hadj = window.scroller.get_hadjustment()
            hadj.set_value(min(100, hadj.get_upper() - hadj.get_page_size()))
            x, y, w, h = window.image_bounds()
            window.drag.emit('drag-begin', x + w * .25, y + h * .25)
            window.drag.emit('drag-update', w * .5, h * .5)
            window.drag.emit('drag-end', w * .5, h * .5)
            for actual, expected in zip(window.rectangle(), selected):
                self.assertAlmostEqual(actual, expected, places=2)
            from gi.repository import Gdk
            pointer = window.scroller.get_width() * .65, window.scroller.get_height() * .6
            window.pointer = pointer
            ctrl = SimpleNamespace(get_current_event_state=lambda: Gdk.ModifierType.CONTROL_MASK)
            plain = SimpleNamespace(get_current_event_state=lambda: Gdk.ModifierType(0))
            old_zoom = window.zoom
            self.assertFalse(window.zoom_scroll(plain, 0, -1))
            self.assertEqual(window.zoom, old_zoom)
            vadj = window.scroller.get_vadjustment()
            x, y, w, h = window.image_bounds()
            point = ((pointer[0] + hadj.get_value() - x) / w,
                     (pointer[1] + vadj.get_value() - y) / h)
            for direction in (-1, 1):
                window.pointer = pointer
                with patch.object(window, 'restore_zoom_anchor', return_value=False):
                    self.assertTrue(window.zoom_scroll(ctrl, 0, direction))
                    until(lambda: not window.busy)
                    pending_anchor = window.zoom_anchor
                    self.assertIsNotNone(pending_anchor)
                    # Um segundo evento não pode usar o canvas ainda na escala anterior.
                    self.assertTrue(window.zoom_scroll(ctrl, 0, direction))
                    self.assertFalse(window.busy)
                    self.assertEqual(window.zoom_anchor, pending_anchor)
                GLib.idle_add(window.restore_zoom_anchor)
                until(lambda: not window.busy and window.zoom_anchor is None)
                x, y, w, h = window.image_bounds()
                self.assertAlmostEqual(x + point[0] * w - hadj.get_value(), pointer[0], delta=1)
                self.assertAlmostEqual(y + point[1] * h - vadj.get_value(), pointer[1], delta=1)
                self.assertEqual(window.rectangle(), selected)
            window.zoom_fit.emit('clicked')
            until(lambda: not window.busy and not window.zoom_layout_pending and window.zoom == 1)
            until(lambda: window.canvas.get_width() <= window.scroller.get_width())
            window.next_button.emit('clicked')
            until(lambda: window.page == 1 and not window.busy)
            window.all_pages.set_active(True)
            window.save_button.emit('clicked')
            until(lambda: not window.busy and bool(list(self.folder.glob('*recorte.pdf'))))
            self.assertIn('Salvo', window.status.get_text())
            screenshot = os.environ.get('CROP_SCREENSHOT')
            if screenshot:
                # Aguarda o próximo frame após atualizar o texto de sucesso.
                frame_ready = []
                GLib.timeout_add(200, lambda: frame_ready.append(True) and False)
                until(lambda: bool(frame_ready))
                snapshot = Gtk.Snapshot()
                widget = window
                Gtk.WidgetPaintable.new(widget).snapshot(snapshot, widget.get_width(), widget.get_height())
                texture = window.get_renderer().render_texture(snapshot.to_node(), None)
                texture.save_to_png(screenshot)
        finally:
            window.destroy()
