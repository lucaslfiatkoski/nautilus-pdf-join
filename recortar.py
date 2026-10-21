"""Janela de recorte local; executada em um processo separado do Nautilus."""
import math
from pathlib import Path
import sys
import tempfile
import threading

import cairo
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk


def fit_rect(width, height, available_width, available_height):
    scale = min(available_width / width, available_height / height)
    w, h = width * scale, height * scale
    return (available_width - w) / 2, (available_height - h) / 2, w, h


def drag_rect(start, end):
    x1, y1 = (min(1, max(0, n)) for n in start)
    x2, y2 = (min(1, max(0, n)) for n in end)
    return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)


def validate_rect(rectangle):
    x, y, w, h = rectangle
    if (not all(math.isfinite(n) for n in rectangle) or min(x, y) < 0 or
            min(w, h) <= 0 or x + w > 1.000001 or y + h > 1.000001):
        raise ValueError('Selecione uma área dentro da prévia, com largura e altura maiores que zero.')
    return x, y, w, h


class CropDocument:
    def __init__(self, path):
        from conversor import _run
        self.path = Path(path).absolute()
        mime = Gio.File.new_for_path(str(self.path)).query_info(
            'standard::content-type', Gio.FileQueryInfoFlags.NONE, None).get_content_type()
        self.pdf = mime == 'application/pdf'
        self.document = None
        if self.pdf:
            gi.require_version('Poppler', '0.18')
            from gi.repository import Poppler
            self.document = Poppler.Document.new_from_file(self.path.as_uri(), None)
            self.count = self.document.get_n_pages()
            if not self.count:
                raise ValueError('O PDF não possui páginas.')
        elif mime and mime.startswith('image/'):
            self.count = 1
            with tempfile.TemporaryDirectory(prefix='recorte-previa-') as temp:
                normalized = Path(temp) / 'imagem.png'
                # shortcut: imagens com vários quadros usam o primeiro; ampliar se houver pedido de animação.
                _run(['magick', str(self.path) + '[0]', '-auto-orient', str(normalized)])
                self.image = cairo.ImageSurface.create_from_png(str(normalized))
        else:
            raise ValueError('Selecione uma imagem ou um PDF.')

    def size(self, page):
        if not 0 <= page < self.count:
            raise ValueError('Página inválida.')
        if self.pdf:
            return self.document.get_page(page).get_size()
        return self.image.get_width(), self.image.get_height()

    def preview(self, page):
        width, height = self.size(page)
        if not self.pdf:
            return self.image
        scale = min(1.5, 1400 / width, 1000 / height)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                     max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale)))
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()
        ctx.scale(scale, scale)
        self.document.get_page(page).render_for_printing(ctx)
        return surface

    def save(self, rectangle, page, all_pages):
        from conversor import _publish
        x, y, w, h = validate_rect(rectangle)
        self.size(page)
        extension = 'pdf' if self.pdf else 'png'
        with tempfile.TemporaryDirectory(prefix='.recorte-', dir=self.path.parent) as temp:
            result = Path(temp) / ('resultado.' + extension)
            if self.pdf:
                surface = cairo.PDFSurface(str(result), 1, 1)
                try:
                    for index in range(self.count):
                        width, height = self.size(index)
                        area = (x * width, y * height, w * width, h * height) if (
                            all_pages or index == page) else (0, 0, width, height)
                        left, top, cw, ch = area
                        surface.set_size(cw, ch)
                        ctx = cairo.Context(surface)
                        ctx.rectangle(0, 0, cw, ch)
                        ctx.clip()
                        ctx.translate(-left, -top)
                        self.document.get_page(index).render_for_printing(ctx)
                        ctx.show_page()
                finally:
                    surface.finish()
            else:
                width, height = self.size(0)
                left, top = math.floor(x * width), math.floor(y * height)
                right = min(width, math.ceil((x + w) * width))
                bottom = min(height, math.ceil((y + h) * height))
                cropped = cairo.ImageSurface(cairo.FORMAT_ARGB32, right - left, bottom - top)
                ctx = cairo.Context(cropped)
                ctx.set_source_surface(self.image, -left, -top)
                ctx.paint()
                cropped.write_to_png(str(result))
            return _publish(result, self.path.with_name(self.path.stem + '_recorte.' + extension))


class CropWindow(Gtk.ApplicationWindow):
    def __init__(self, app, path):
        super().__init__(application=app, title='Recortar — ' + Path(path).name)
        self.set_default_size(660, 600)
        self.set_resizable(False)
        self.document, self.preview_image = None, None
        self.page, self.busy, self.closed = 0, False, False
        self.start = None
        self.connect('close-request', self.closing)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.set_child(box)
        box.append(Gtk.Label(label='Arraste na prévia para escolher a área. Arraste novamente para ajustar.',
                             wrap=True, xalign=0))
        self.canvas = Gtk.DrawingArea(content_width=420, content_height=280, hexpand=True, vexpand=True)
        self.canvas.set_draw_func(self.draw)
        self.canvas.set_cursor_from_name('crosshair')
        self.canvas.update_property([Gtk.AccessibleProperty.LABEL], ['Prévia da área de recorte'])
        box.append(self.canvas)
        self.drag = Gtk.GestureDrag()
        self.drag.set_button(1)
        self.drag.connect('drag-begin', self.begin)
        self.drag.connect('drag-update', self.update)
        self.drag.connect('drag-end', self.update)
        self.canvas.add_controller(self.drag)
        controls = Gtk.Box(spacing=8)
        box.append(controls)
        self.fields = []
        for label, value in (('Esquerda %', 0), ('Topo %', 0), ('Largura %', 100), ('Altura %', 100)):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
            text = Gtk.Label(label=label, xalign=0, use_underline=True)
            spin = Gtk.SpinButton.new_with_range(0, 100, .1)
            spin.set_digits(1)
            spin.set_value(value)
            text.set_mnemonic_widget(spin)
            spin.update_property([Gtk.AccessibleProperty.LABEL], [label])
            spin.connect('value-changed', self.changed)
            column.append(text)
            column.append(spin)
            controls.append(column)
            self.fields.append(spin)
        self.navigation = Gtk.Box(spacing=8)
        self.previous_button = Gtk.Button(label='← Anterior')
        self.next_button = Gtk.Button(label='Próxima →')
        self.page_label = Gtk.Label(hexpand=True)
        self.previous_button.connect('clicked', lambda button: self.change_page(-1))
        self.next_button.connect('clicked', lambda button: self.change_page(1))
        for widget in (self.previous_button, self.page_label, self.next_button):
            self.navigation.append(widget)
        box.append(self.navigation)
        self.all_pages = Gtk.CheckButton(label='Aplicar a mesma área proporcional a todas as páginas')
        box.append(self.all_pages)
        self.note = Gtk.Label(wrap=True, xalign=0)
        self.note.add_css_class('dim-label')
        box.append(self.note)
        self.status = Gtk.Label(label='Carregando prévia…', wrap=True, xalign=0, selectable=True)
        box.append(self.status)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        reset = Gtk.Button(label='Restaurar área')
        reset.connect('clicked', lambda button: self.set_rectangle((0, 0, 1, 1)))
        close = Gtk.Button(label='Fechar')
        close.connect('clicked', lambda button: self.close())
        self.save_button = Gtk.Button(label='Salvar cópia')
        self.save_button.add_css_class('suggested-action')
        self.save_button.connect('clicked', self.save)
        for button in (reset, close, self.save_button):
            buttons.append(button)
        box.append(buttons)
        self.run_job(lambda: self.load(path), self.loaded)

    def closing(self, *args):
        self.closed = True
        return False

    def run_job(self, work, complete):
        self.busy = True
        self.refresh()
        def worker():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)
            GLib.idle_add(finish, result, error)
        def finish(result, error):
            if not self.closed:
                self.busy = False
                if error:
                    self.status.set_text('Não foi possível concluir: ' + error)
                else:
                    complete(result)
                self.refresh()
            return False
        threading.Thread(target=worker, daemon=False).start()

    def load(self, path):
        document = CropDocument(path)
        return document, document.preview(0)

    def loaded(self, result):
        self.document, self.preview_image = result
        self.navigation.set_visible(self.document.pdf)
        self.all_pages.set_visible(self.document.pdf)
        self.note.set_text('Recorte visual: não serve para apagar dados sigilosos. Links, formulários e assinaturas não são preservados.'
                           if self.document.pdf else 'A cópia será PNG. Em imagens animadas ou com várias páginas, recorta apenas o primeiro quadro.')
        self.status.set_text('Escolha a área e clique em Salvar cópia.')
        self.canvas.queue_draw()

    def refresh(self):
        ready = self.document is not None and not self.busy
        valid = False
        if len(self.fields) == 4:
            try:
                validate_rect(self.rectangle())
                valid = True
            except ValueError:
                pass
        self.save_button.set_sensitive(ready and valid)
        self.previous_button.set_sensitive(ready and self.page > 0)
        self.next_button.set_sensitive(ready and self.page + 1 < self.document.count)
        self.all_pages.set_sensitive(ready)
        for field in self.fields:
            field.set_sensitive(ready)
        if self.document:
            self.page_label.set_text(f'Página {self.page + 1} de {self.document.count}')

    def rectangle(self):
        return tuple(field.get_value() / 100 for field in self.fields)

    def set_rectangle(self, rectangle):
        for field, value in zip(self.fields, rectangle):
            field.set_value(value * 100)
        self.changed()

    def changed(self, *args):
        self.canvas.queue_draw()
        if hasattr(self, 'save_button'):
            self.refresh()

    def change_page(self, step):
        if self.busy or not self.document:
            return
        page = self.page + step
        if not 0 <= page < self.document.count:
            return
        self.status.set_text('Carregando página…')
        def shown(image):
            self.page, self.preview_image = page, image
            self.status.set_text('Escolha a área e clique em Salvar cópia.')
            self.canvas.queue_draw()
        self.run_job(lambda: self.document.preview(page), shown)

    def image_bounds(self):
        return fit_rect(self.preview_image.get_width(), self.preview_image.get_height(),
                        self.canvas.get_width(), self.canvas.get_height())

    def begin(self, gesture, x, y):
        self.start = None
        if self.busy or self.preview_image is None:
            return
        left, top, w, h = self.image_bounds()
        if left <= x <= left + w and top <= y <= top + h:
            self.start = ((x - left) / w, (y - top) / h)

    def update(self, gesture, dx, dy):
        if self.busy or self.start is None:
            return
        _, _, w, h = self.image_bounds()
        end = self.start[0] + dx / w, self.start[1] + dy / h
        self.set_rectangle(drag_rect(self.start, end))

    def draw(self, area, ctx, width, height):
        ctx.set_source_rgb(.16, .16, .18)
        ctx.paint()
        if self.preview_image is None:
            return
        left, top, w, h = self.image_bounds()
        ctx.save()
        ctx.translate(left, top)
        ctx.scale(w / self.preview_image.get_width(), h / self.preview_image.get_height())
        ctx.set_source_surface(self.preview_image, 0, 0)
        ctx.paint()
        ctx.restore()
        x, y, rw, rh = self.rectangle()
        x, y, rw, rh = left + x * w, top + y * h, rw * w, rh * h
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        ctx.rectangle(left, top, w, h)
        ctx.rectangle(x, y, rw, rh)
        ctx.set_source_rgba(0, 0, 0, .5)
        ctx.fill()
        ctx.rectangle(x, y, rw, rh)
        ctx.set_source_rgb(1, .55, .15)
        ctx.set_line_width(2)
        ctx.stroke()

    def save(self, button):
        if self.busy or self.document is None:
            return
        rectangle, page, all_pages = self.rectangle(), self.page, self.all_pages.get_active()
        try:
            validate_rect(rectangle)
        except ValueError as error:
            self.status.set_text(str(error))
            return
        self.status.set_text('Salvando cópia…')
        self.run_job(lambda: self.document.save(rectangle, page, all_pages),
                     lambda result: self.status.set_text('Salvo: ' + result.name))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Uso: recortar.py ARQUIVO')
    source = sys.argv[1]
    application = Gtk.Application(application_id='br.local.NautilusRecorte', flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.connect('activate', lambda app: CropWindow(app, source).present())
    sys.exit(application.run([sys.argv[0]]))
