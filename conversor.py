"""Conversões locais e círculo de formatos para o Nautilus."""

import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Nautilus', '4.1')
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Nautilus


def selection_paths(model):
    paths = []
    selected = model.get_selection()
    for index in range(selected.get_size()):
        item = model.get_item(selected.get_nth(index))
        if isinstance(item, Gtk.TreeListRow):
            item = item.get_item()
        # shortcut: depende do modelo interno do Nautilus; rever após mudanças na sua API.
        if item is None or item.find_property('file') is None:
            return []
        file = item.get_property('file')
        if not isinstance(file, Nautilus.FileInfo) or file.is_directory():
            return []
        path = file.get_location().get_path()
        if not path:
            return []
        paths.append(path)
    return paths


class ShiftGesture:
    def __init__(self):
        self.pending = False

    def press(self, key, other_modifiers):
        self.pending = key in ('Shift_L', 'Shift_R') and not other_modifiers

    def release(self, key):
        if key not in ('Shift_L', 'Shift_R'):
            return False
        pending, self.pending = self.pending, False
        return pending


def sector_at(x, y, count):
    dx, dy = x - 160, y - 160
    if not count or not 64 <= math.hypot(dx, dy) <= 154:
        return None
    angle = (math.atan2(dy, dx) + math.pi / 2 + math.pi / count) % math.tau
    return int(angle / math.tau * count) % count


class FormatWheel:
    def __init__(self, parent, paths):
        self.paths = paths
        self.actions = available_actions(paths)
        self.highlight = 0 if self.actions else None
        self.popover = Gtk.Popover(has_arrow=False, autohide=True)
        self.popover.add_css_class('conversion-wheel')
        self.popover.set_parent(parent)
        point = Gdk.Rectangle()
        point.x, point.y = parent.get_width() // 2, parent.get_height() // 2
        point.width = point.height = 1
        self.popover.set_pointing_to(point)
        self.popover.set_position(Gtk.PositionType.BOTTOM)
        self.popover.connect('closed', lambda popover: popover.unparent())
        fixed = Gtk.Fixed(width_request=320, height_request=320)
        self.popover.set_child(fixed)
        self.canvas = Gtk.DrawingArea(content_width=320, content_height=320)
        self.canvas.set_draw_func(self.draw)
        fixed.put(self.canvas, 0, 0)
        for index, (kind, label) in enumerate(self.actions):
            angle = -math.pi / 2 + math.tau * index / len(self.actions)
            button = Gtk.Button(label=label)
            button.set_size_request(86, 44)
            button.add_css_class('wheel-choice')
            button.set_tooltip_text('Unir os PDFs selecionados' if kind == 'join' else f'Converter para {label}')
            button.connect('clicked', lambda button, i=index: self.activate(i))
            button.connect('notify::has-focus', self.button_focus, index)
            fixed.put(button, 160 + 108 * math.cos(angle) - 43,
                      160 + 108 * math.sin(angle) - 22)
        motion = Gtk.EventControllerMotion()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect('motion', self.motion)
        fixed.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect('released', self.click)
        self.canvas.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key)
        self.popover.add_controller(keys)
        self.popover.popup()

    def draw(self, area, context, width, height):
        count = len(self.actions)
        if not count:
            context.set_source_rgba(.10, .09, .12, .98)
            context.arc(160, 160, 154, 0, math.tau)
            context.fill()
        for index in range(count):
            center = -math.pi / 2 + math.tau * index / count
            start, end = center - math.pi / count + .025, center + math.pi / count - .025
            context.set_source_rgba(*((.91, .36, .10, .99) if index == self.highlight else (.13, .12, .16, .99)))
            context.arc(160, 160, 154, start, end)
            context.arc_negative(160, 160, 64, end, start)
            context.close_path()
            context.fill()
        context.set_source_rgba(.08, .07, .10, .99)
        context.arc(160, 160, 59, 0, math.tau)
        context.fill()
        context.set_source_rgb(1, .65, .35)
        context.select_font_face('Sans', 0, 1)
        context.set_font_size(13)
        title = 'Converter' if count else 'Sem opções'
        context.move_to(160 - context.text_extents(title).width / 2, 156)
        context.show_text(title)
        context.set_source_rgb(.82, .80, .85)
        context.set_font_size(11)
        text = f'{len(self.paths)} arquivo' + ('s' if len(self.paths) != 1 else '')
        context.move_to(160 - context.text_extents(text).width / 2, 176)
        context.show_text(text)

    def motion(self, controller, x, y):
        self.highlight = sector_at(x, y, len(self.actions))
        self.canvas.queue_draw()

    def button_focus(self, button, pspec, index):
        if button.has_focus():
            self.highlight = index
            self.canvas.queue_draw()

    def click(self, gesture, presses, x, y):
        index = sector_at(x, y, len(self.actions))
        if index is not None:
            self.activate(index)
        else:
            self.popover.popdown()

    def key(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_Right, Gdk.KEY_Down) and self.actions:
            step = -1 if keyval in (Gdk.KEY_Left, Gdk.KEY_Up) else 1
            self.highlight = ((self.highlight or 0) + step) % len(self.actions)
            self.canvas.queue_draw()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.highlight is not None:
            self.activate(self.highlight)
            return True
        return False

    def activate(self, index):
        kind = self.actions[index][0]
        self.popover.popdown()
        if kind == 'join':
            command = ['/usr/bin/python3', str(Path(__file__).with_name('juntar_pdfs.py')), *self.paths]
        else:
            command = ['/usr/bin/python3', str(Path(__file__).resolve()), '--convert', kind, *self.paths]
        try:
            subprocess.Popen(command)
        except OSError as error:
            subprocess.Popen(['zenity', '--error', '--no-markup', '--text=' + str(error)])


class WindowShortcut:
    def __init__(self, window):
        self.window = window
        self.gesture = ShiftGesture()
        self.wheel = None
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.press)
        keys.connect('key-released', self.release)
        window.add_controller(keys)
        click = Gtk.GestureClick()
        click.set_button(0)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', lambda *args: self.gesture.press('pointer', False))
        window.add_controller(click)
        window.connect('notify::is-active', self.focus_changed)

    def focus_changed(self, window, pspec):
        if not window.is_active():
            self.gesture.pending = False

    def selected_view(self):
        widget = self.window.get_focus()
        while widget:
            if isinstance(widget, (Gtk.Editable, Gtk.TextView)):
                return None
            if isinstance(widget, (Gtk.GridView, Gtk.ColumnView)):
                return widget
            widget = widget.get_parent()
        return None

    def press(self, controller, keyval, keycode, state):
        modifiers = state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK |
                             Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.META_MASK |
                             Gdk.ModifierType.BUTTON1_MASK | Gdk.ModifierType.BUTTON2_MASK |
                             Gdk.ModifierType.BUTTON3_MASK)
        self.gesture.press(Gdk.keyval_name(keyval), bool(modifiers))
        return False

    def release(self, controller, keyval, keycode, state):
        if not self.gesture.release(Gdk.keyval_name(keyval)):
            return
        if self.wheel and self.wheel.popover.get_visible():
            return
        view = self.selected_view()
        if view is None:
            return
        paths = selection_paths(view.get_model())
        if paths:
            self.wheel = FormatWheel(view, paths)


def install_shortcut():
    css = Gtk.CssProvider()
    css.load_from_string('''
        .conversion-wheel > contents { background: transparent; border: none;
            box-shadow: none; padding: 0; }
        .wheel-choice { background: transparent; border: none; box-shadow: none;
            color: white; font-weight: bold; font-size: 13px; padding: 0; }
        .wheel-choice:hover { background: rgba(255,255,255,0.10); }
    ''')
    display = Gdk.Display.get_default()
    if display is None:
        return
    Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    windows = Gtk.Window.get_toplevels()

    def attach(*args):
        for window in windows:
            if window.__gtype__.name == 'NautilusWindow' and not hasattr(window, '_conversion_shortcut'):
                window._conversion_shortcut = WindowShortcut(window)

    windows.connect('items-changed', attach)
    attach()


def available_actions(paths):
    if not paths:
        return []
    types = []
    for path in paths:
        try:
            info = Gio.File.new_for_path(str(path)).query_info(
                'standard::type,standard::content-type', Gio.FileQueryInfoFlags.NONE, None)
        except GLib.Error:
            return []
        if info.get_file_type() != Gio.FileType.REGULAR:
            return []
        types.append(info.get_content_type() or '')
    if all(t == 'application/pdf' for t in types):
        actions = [('join', 'Juntar PDFs')] if len(paths) > 1 else []
        if shutil.which('pdftotext'):
            actions.append(('txt', 'Texto'))
        if shutil.which('pdftoppm'):
            actions.extend([('png', 'PNG'), ('jpg', 'JPG')])
        return actions
    if all(t.startswith('image/') for t in types) and shutil.which('magick'):
        return [(ext, label) for ext, label in [('png', 'PNG'), ('jpg', 'JPG'),
                ('webp', 'WebP'), ('avif', 'AVIF'), ('tiff', 'TIFF'), ('pdf', 'PDF')]]
    if all(t.startswith(('audio/', 'video/')) for t in types) and shutil.which('ffmpeg'):
        actions = [('mp3', 'MP3'), ('wav', 'WAV'), ('flac', 'FLAC'), ('ogg', 'OGG')]
        if all(t.startswith('video/') for t in types):
            actions = [('mp4', 'MP4'), ('webm', 'WebM')] + actions
        return actions
    return []


def _run(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as error:
        raise ValueError('A conversão excedeu o limite de 3 minutos.') from error
    if result.returncode:
        raise ValueError(result.stderr.strip()[-1200:] or 'O conversor não conseguiu ler o arquivo.')


def _publish(source, destination):
    number = 1
    while True:
        candidate = destination if number == 1 else destination.with_stem(f'{destination.stem}_{number}')
        try:
            # O link publica o arquivo completo e recusa colisões, inclusive links simbólicos.
            os.link(source, candidate)
            return candidate
        except FileExistsError:
            number += 1


def convert_files(kind, paths):
    paths = [Path(p).absolute() for p in paths]
    if kind == 'join' or kind not in dict(available_actions(paths)):
        raise ValueError('Essa conversão não está disponível para a seleção.')
    outputs, errors = [], []
    for path in paths:
        try:
            with tempfile.TemporaryDirectory(prefix='.conversao-', dir=path.parent) as temp:
                folder = Path(temp)
                target = folder / ('resultado.' + kind)
                mime = Gio.File.new_for_path(str(path)).query_info(
                    'standard::content-type', Gio.FileQueryInfoFlags.NONE, None).get_content_type()
                if mime == 'application/pdf':
                    if kind == 'txt':
                        _run(['pdftotext', '-layout', str(path), str(target)])
                    else:
                        _run(['pdftoppm', '-r', '200', '-png' if kind == 'png' else '-jpeg',
                              str(path), str(folder / 'pagina')])
                elif mime.startswith('image/'):
                    command = ['magick', str(path)]
                    if kind == 'jpg':
                        command += ['-background', 'white', '-alpha', 'remove', '-alpha', 'off']
                    _run(command + [str(folder / f'resultado-%06d.{kind}')])
                else:
                    _run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(path),
                          *(['-vn'] if kind in ('mp3', 'wav', 'flac', 'ogg') else []), str(target)])
                files = sorted(folder.iterdir())
                if not files:
                    raise ValueError('Nenhum arquivo foi produzido pelo conversor.')
                for index, file in enumerate(files, 1):
                    stem = path.stem if len(files) == 1 else f'{path.stem}_pagina_{index}'
                    outputs.append(_publish(file, path.with_name(f'{stem}.{kind}')))
        except (OSError, ValueError, GLib.Error) as error:
            errors.append(f'{path.name}: {error}')
    if errors:
        raise ValueError('\n\n'.join(errors) +
                         (f'\n\n{len(outputs)} resultado(s) já criado(s) foram preservados.' if outputs else ''))
    return outputs


if __name__ == '__main__':
    try:
        convert_files(sys.argv[2], sys.argv[3:])
    except (OSError, ValueError) as error:
        subprocess.run(['zenity', '--error', '--no-markup', '--title=Converter arquivos',
                        '--text=' + str(error)[:5000]])
        sys.exit(1)
