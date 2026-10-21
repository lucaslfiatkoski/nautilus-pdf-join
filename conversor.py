"""Conversões locais e círculo de formatos para o Nautilus."""

import bz2
import gzip
import lzma
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Nautilus', '4.1')
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Nautilus

IMAGE_OUTPUTS = ('png', 'jpg', 'webp', 'heic', 'tiff', 'avif', 'bmp', 'gif',
                 'ico', 'jp2', 'jxl', 'qoi', 'tga', 'pdf')
AUDIO_CODECS = {'mp3': 'libmp3lame', 'm4a': 'aac', 'wav': 'pcm_s16le', 'flac': 'flac',
                'ogg': 'libvorbis', 'opus': 'libopus', 'aiff': 'pcm_s16be',
                'wma': 'wmav2', 'aac': 'aac'}
VIDEO_CODECS = {'mp4': ('libx264', 'aac'), 'mov': ('libx264', 'aac'),
                'mkv': ('libx264', 'aac'), 'webm': ('libvpx-vp9', 'libopus'),
                'avi': ('mpeg4', 'libmp3lame'), 'wmv': ('wmv2', 'wmav2')}
DOCUMENT_READERS = {'md': 'markdown', 'markdown': 'markdown', 'txt': 'markdown',
                    'html': 'html', 'htm': 'html', 'docx': 'docx', 'odt': 'odt',
                    'rtf': 'rtf', 'epub': 'epub', 'tex': 'latex', 'rst': 'rst',
                    'org': 'org', 'fb2': 'fb2', 'ipynb': 'ipynb'}
DOCUMENT_WRITERS = {'docx': 'docx', 'odt': 'odt', 'rtf': 'rtf', 'md': 'markdown',
                    'txt': 'plain', 'html': 'html5', 'epub': 'epub3',
                    'rst': 'rst', 'tex': 'latex', 'org': 'org', 'fb2': 'fb2'}
OFFICE_READERS = ('docx', 'doc', 'odt', 'rtf', 'txt', 'html', 'htm', 'pages')
SPREADSHEETS = ('xlsx', 'ods', 'xls', 'csv', 'tsv', 'fods')
SLIDES = ('pptx', 'ppt', 'odp')
ARCHIVES = ('zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', '7z')
SUBTITLES = ('srt', 'vtt', 'ass', 'ssa')


def tool(name):
    found = shutil.which(name)
    local = Path.home() / '.local/bin' / name
    return found or (str(local) if os.access(local, os.X_OK) else None)


def file_category(path, mime):
    suffix = Path(path).suffix.lower().lstrip('.')
    if mime == 'application/pdf':
        return 'pdf'
    for category in ('image', 'video', 'audio'):
        if mime.startswith(category + '/'):
            return category
    if suffix in SPREADSHEETS:
        return 'sheet'
    if suffix in SLIDES:
        return 'slides'
    if suffix in SUBTITLES:
        return 'subtitle'
    if suffix in DOCUMENT_READERS or suffix in ('doc', 'pages'):
        return 'document'
    if suffix in ('zip', 'tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz', 'txz', '7z', 'rar'):
        return 'archive'
    return ''


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


def action_page(actions, page):
    count = max(1, (len(actions) + 5) // 6)
    page %= count
    return actions[page * 6:(page + 1) * 6], page, count


class FormatWheel:
    def __init__(self, parent, paths):
        self.paths = paths
        self.all_actions = available_actions(paths)
        self.actions, self.page, self.page_count = action_page(self.all_actions, 0)
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
        self.fixed, self.buttons = fixed, []
        self.add_choices()
        if self.page_count > 1:
            for direction, label, x in ((-1, '‹', 112), (1, '›', 182)):
                button = Gtk.Button(label=label)
                button.add_css_class('wheel-choice')
                button.set_size_request(26, 26)
                button.set_tooltip_text('Formatos anteriores' if direction < 0 else 'Próximos formatos')
                button.connect('clicked', lambda button, step=direction: self.change_page(step))
                fixed.put(button, x, 166)
            scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL |
                                                   Gtk.EventControllerScrollFlags.DISCRETE)
            scroll.connect('scroll', self.scroll)
            fixed.add_controller(scroll)
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

    def add_choices(self):
        for index, (kind, label) in enumerate(self.actions):
            angle = -math.pi / 2 + math.tau * index / len(self.actions)
            button = Gtk.Button(label=label)
            button.set_size_request(86, 44)
            button.add_css_class('wheel-choice')
            button.set_tooltip_text('Unir os PDFs selecionados' if kind == 'join' else f'Converter para {label}')
            button.connect('clicked', lambda button, i=index: self.activate(i))
            button.connect('notify::has-focus', self.button_focus, index)
            self.fixed.put(button, 160 + 108 * math.cos(angle) - 43,
                           160 + 108 * math.sin(angle) - 22)
            self.buttons.append(button)

    def change_page(self, step):
        for button in self.buttons:
            self.fixed.remove(button)
        self.buttons.clear()
        self.actions, self.page, self.page_count = action_page(self.all_actions, self.page + step)
        self.highlight = 0 if self.actions else None
        self.add_choices()
        self.canvas.queue_draw()

    def scroll(self, controller, dx, dy):
        if dy:
            self.change_page(1 if dy > 0 else -1)
        return True

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
        context.move_to(160 - context.text_extents(title).width / 2, 146 if self.page_count > 1 else 156)
        context.show_text(title)
        context.set_source_rgb(.82, .80, .85)
        context.set_font_size(11)
        text = f'{len(self.paths)} arquivo' + ('s' if len(self.paths) != 1 else '')
        context.move_to(160 - context.text_extents(text).width / 2, 163 if self.page_count > 1 else 176)
        context.show_text(text)
        if self.page_count > 1:
            text = f'{self.page + 1}/{self.page_count}'
            context.move_to(160 - context.text_extents(text).width / 2, 184)
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
        if keyval in (Gdk.KEY_Page_Up, Gdk.KEY_Page_Down):
            self.change_page(-1 if keyval == Gdk.KEY_Page_Up else 1)
            return True
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
    categories = []
    for path in paths:
        try:
            info = Gio.File.new_for_path(str(path)).query_info(
                'standard::type,standard::content-type', Gio.FileQueryInfoFlags.NONE, None)
        except GLib.Error:
            return []
        if info.get_file_type() != Gio.FileType.REGULAR:
            return []
        categories.append(file_category(path, info.get_content_type() or ''))
    if len(set(categories)) != 1:
        return []
    category = categories[0]
    if category == 'pdf':
        actions = [('join', 'Juntar PDFs')] if len(paths) > 1 else []
        if tool('pdftotext'):
            actions.append(('txt', 'Texto'))
            if tool('pandoc'):
                actions.extend((ext, ext.upper() + '\n(texto)')
                               for ext in ('docx', 'odt', 'rtf', 'md', 'html', 'epub'))
        if tool('pdftoppm'):
            actions.extend([('png', 'PNG'), ('jpg', 'JPG')])
        return actions
    if category == 'image' and tool('magick'):
        return [(ext, ext.upper()) for ext in IMAGE_OUTPUTS]
    if category in ('audio', 'video') and tool('ffmpeg'):
        formats = list(AUDIO_CODECS)
        if category == 'video':
            formats = [*VIDEO_CODECS, 'gif', *formats]
        return [(ext, ext.upper()) for ext in formats]
    if category == 'subtitle' and tool('ffmpeg'):
        return [(ext, ext.upper()) for ext in (*SUBTITLES, 'txt')]
    if category == 'archive' and tool('bsdtar'):
        return [(ext, ext.upper()) for ext in ARCHIVES]
    if category == 'document':
        if not tool('pandoc') and any(Path(p).suffix.lower().lstrip('.') not in OFFICE_READERS for p in paths):
            return []
        formats = list(DOCUMENT_WRITERS) if tool('pandoc') else []
        if tool('libreoffice'):
            formats = list(dict.fromkeys([*formats, 'docx', 'odt', 'doc', 'rtf', 'txt',
                                         'html', 'epub', 'pdf', 'png', 'jpg']))
        if not tool('libreoffice') and any(Path(p).suffix.lower() in ('.doc', '.pages') for p in paths):
            return []
        return [(ext, ext.upper()) for ext in formats]
    if category in ('sheet', 'slides') and tool('libreoffice'):
        formats = SPREADSHEETS if category == 'sheet' else SLIDES
        extras = ('pdf', 'html', 'png', 'jpg') if category == 'sheet' else ('pdf', 'png', 'jpg')
        return [(ext, ext.upper()) for ext in (*formats, *extras)]
    return []


def _run(command):
    if not command or not command[0]:
        raise ValueError('Uma ferramenta necessária para esta conversão não está instalada.')
    if '/' not in command[0]:
        executable = tool(command[0])
        if not executable:
            raise ValueError(f'Ferramenta não encontrada: {command[0]}.')
        command = [executable, *command[1:]]
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


def _pandoc(source, target):
    executable = tool('pandoc')
    if not executable:
        raise ValueError('O Pandoc é necessário para esta conversão e não está instalado.')
    reader = DOCUMENT_READERS.get(source.suffix.lower().lstrip('.'), 'markdown')
    writer = DOCUMENT_WRITERS[target.suffix.lstrip('.')]
    command = [executable, '--sandbox', '--standalone', '--from', reader,
               '--to', writer, '--output', str(target)]
    if target.suffix == '.html':
        command.append('--embed-resources')
    _run([*command, str(source)])


def _office(source, kind, folder):
    folder.mkdir(parents=True, exist_ok=True)
    profile = folder / 'profile'
    profile.mkdir()
    (profile / 'registrymodifications.xcu').write_text('''<?xml version="1.0"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
</item></oor:items>''')
    output = folder / 'output'
    output.mkdir()
    export = kind
    if kind == 'html':
        filter_name = 'HTML (StarCalc)' if source.suffix.lstrip('.').lower() in SPREADSHEETS else 'HTML (StarWriter)'
        export = f'html:{filter_name}:EmbedImages'
    elif kind in ('csv', 'tsv'):
        separator = 44 if kind == 'csv' else 9
        export = f'{kind}:Text - txt - csv (StarCalc):{separator},34,76,1,,0,false,true,true,false,false,-1'
    command = [tool('libreoffice'), '-env:UserInstallation=' + profile.as_uri(),
               '--headless', '--norestore', '--nodefault', '--convert-to', export,
               '--outdir', str(output)]
    if source.suffix.lower() in ('.csv', '.tsv'):
        separator = 44 if source.suffix.lower() == '.csv' else 9
        command.append(f'--infilter=Text - txt - csv (StarCalc):{separator},34,76,1,,0,false,false,false,false,false,0,false')
    _run([*command, str(source)])
    files = sorted(p for p in output.iterdir() if p.is_file())
    if not files:
        raise ValueError('O LibreOffice não conseguiu exportar esse formato.')
    return files


def _document(source, kind, folder, category):
    auxiliary = folder / 'auxiliary'
    auxiliary.mkdir()
    if category in ('sheet', 'slides'):
        office_kind = 'pdf' if kind in ('png', 'jpg') else kind
        results = _office(source, office_kind, auxiliary / 'office')
    else:
        extension = source.suffix.lower().lstrip('.')
        office_writers = ('docx', 'doc', 'odt', 'rtf', 'txt', 'html', 'epub', 'pdf')
        office_kind = 'pdf' if kind in ('png', 'jpg') else kind
        if tool('libreoffice') and extension in OFFICE_READERS and office_kind in office_writers:
            results = _office(source, office_kind, auxiliary / 'office')
        else:
            if extension not in DOCUMENT_READERS:
                source = _office(source, 'docx', auxiliary / 'import')[0]
            if kind in DOCUMENT_WRITERS:
                _pandoc(source, folder / ('resultado.' + kind))
                return
            intermediate = auxiliary / 'documento.docx'
            _pandoc(source, intermediate)
            results = _office(intermediate, office_kind, auxiliary / 'office')
    if kind in ('png', 'jpg'):
        _run(['pdftoppm', '-r', '200', '-png' if kind == 'png' else '-jpeg',
              str(results[0]), str(folder / 'pagina')])
    else:
        for result in results:
            shutil.move(str(result), folder / result.name)


def _subtitle(source, kind, target, folder):
    if kind != 'txt':
        _run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(source),
              '-map', '0:s:0', str(target)])
        return
    auxiliary = folder / 'auxiliary'
    auxiliary.mkdir()
    srt = auxiliary / 'legenda.srt'
    _run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(source), str(srt)])
    blocks = re.split(r'\n\s*\n', srt.read_text())
    text = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) >= 3 and lines[0].isdigit() and '-->' in lines[1]:
            text.append('\n'.join(lines[2:]))
    target.write_text('\n\n'.join(text) + '\n')


def _archive(source, kind, target):
    compression = {'tar.gz': 'z', 'tar.bz2': 'j', 'tar.xz': 'J'}.get(kind, '')
    format_name = 'zip' if kind == 'zip' else '7zip' if kind == '7z' else 'pax'
    command = ['bsdtar', '--format', format_name, '-c' + compression + 'f', str(target)]
    try:
        _run([*command, '@' + str(source)])
    except ValueError:
        openers = {'.gz': gzip.open, '.bz2': bz2.open, '.xz': lzma.open}
        opener = openers.get(source.suffix.lower())
        if not opener or any(source.name.lower().endswith('.' + ext) for ext in ARCHIVES):
            raise
        auxiliary = target.parent / 'auxiliary'
        auxiliary.mkdir()
        unpacked = auxiliary / source.stem
        try:
            with opener(source, 'rb') as compressed, unpacked.open('xb') as output:
                shutil.copyfileobj(compressed, output)
        except (EOFError, lzma.LZMAError) as error:
            raise ValueError('Arquivo compactado inválido.') from error
        _run([*command, '-C', str(auxiliary), './' + unpacked.name])


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
                category = file_category(path, mime)
                if category == 'pdf':
                    if kind == 'txt':
                        _run(['pdftotext', '-layout', str(path), str(target)])
                    elif kind in ('png', 'jpg'):
                        _run(['pdftoppm', '-r', '200', '-png' if kind == 'png' else '-jpeg',
                              str(path), str(folder / 'pagina')])
                    else:
                        auxiliary = folder / 'auxiliary'
                        auxiliary.mkdir()
                        text = auxiliary / 'documento.txt'
                        _run(['pdftotext', '-layout', str(path), str(text)])
                        _pandoc(text, target)
                elif category == 'image':
                    command = ['magick', str(path), '-coalesce']
                    if kind == 'jpg':
                        command += ['-background', 'white', '-alpha', 'remove', '-alpha', 'off']
                    if kind == 'ico':
                        command += ['-resize', '256x256>']
                    _run(command + [str(folder / f'resultado-%06d.{kind}')])
                elif category in ('audio', 'video'):
                    if kind in AUDIO_CODECS:
                        options = ['-vn', '-c:a', AUDIO_CODECS[kind]]
                    elif kind == 'gif':
                        options = ['-an', '-vf', 'fps=15', '-loop', '0']
                    else:
                        video, audio = VIDEO_CODECS[kind]
                        options = ['-c:v', video, '-c:a', audio, '-pix_fmt', 'yuv420p',
                                   '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2']
                    _run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(path),
                          *options, str(target)])
                elif category in ('document', 'sheet', 'slides'):
                    _document(path, kind, folder, category)
                elif category == 'subtitle':
                    _subtitle(path, kind, target, folder)
                elif category == 'archive':
                    _archive(path, kind, target)
                files = sorted(p for p in folder.iterdir() if p.is_file())
                if not files:
                    raise ValueError('Nenhum arquivo foi produzido pelo conversor.')
                for index, file in enumerate(files, 1):
                    stem = path.stem if len(files) == 1 else f'{path.stem}_pagina_{index}'
                    if category == 'sheet' and len(files) > 1:
                        stem = file.stem
                    if category == 'archive':
                        stem = path.name
                        for suffix in (*ARCHIVES, 'tgz', 'tbz2', 'txz', 'rar', 'gz', 'bz2', 'xz'):
                            if stem.lower().endswith('.' + suffix):
                                stem = stem[:-len(suffix)-1]
                                break
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
