"""Teste opcional da paginação no componente GTK real."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cairo
from conversor import FormatWheel, Gtk, GLib, install_shortcut


@unittest.skipUnless(os.environ.get('RUN_WHEEL_UI') == '1', 'Requer uma sessão gráfica de teste.')
class WheelUiTests(unittest.TestCase):
    def test_visible_pages_and_navigation_buttons(self):
        Gtk.init()
        install_shortcut()
        with tempfile.TemporaryDirectory(prefix='circulo-ui-') as temp:
            image = Path(temp) / 'demonstracao.png'
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
            surface.write_to_png(str(image))
            window = Gtk.Window(title='Verificação do círculo de conversão')
            window.set_default_size(600,600)
            parent = Gtk.MenuButton(label='Imagem sintética selecionada')
            window.set_child(parent)
            loop, errors, state = GLib.MainLoop(), [], {}

            def finish():
                if state.get('wheel') and state['wheel'].popover.get_parent():
                    state['wheel'].popover.unparent()
                window.destroy()
                loop.quit()

            def check():
                try:
                    wheel = state['wheel']
                    self.assertTrue(wheel.popover.get_mapped())
                    self.assertGreater(wheel.popover.get_width(),0)
                    self.assertEqual(len(wheel.buttons),6)
                    first = list(wheel.actions)
                    child = wheel.fixed.get_first_child()
                    while child:
                        if isinstance(child,Gtk.Button) and child.get_label() == '›':
                            child.emit('clicked')
                            break
                        child = child.get_next_sibling()
                    self.assertEqual(wheel.page,1)
                    self.assertNotEqual(wheel.actions,first)
                    self.assertLessEqual(len(wheel.buttons),6)
                    wheel.change_page(1)
                    self.assertEqual(wheel.page,2)
                    self.assertEqual(len(wheel.actions),3)
                    wheel.change_page(1)
                    self.assertEqual(wheel.actions,first)
                    state['checked'] = True
                    GLib.timeout_add(200,capture)
                except Exception as error:
                    errors.append(error)
                    finish()
                return False

            def capture():
                try:
                    destination = os.environ.get('WHEEL_SCREENSHOT')
                    if destination:
                        widget = state['wheel'].popover
                        snapshot = Gtk.Snapshot()
                        Gtk.WidgetPaintable.new(widget.get_child()).snapshot(snapshot,320,320)
                        texture = widget.get_native().get_renderer().render_texture(snapshot.to_node(),None)
                        texture.save_to_png(destination)
                except Exception as error:
                    errors.append(error)
                finish()
                return False

            def open_wheel():
                # Sem evento físico no teste, Wayland não fornece serial para um grab modal.
                class UngrabbedPopover(Gtk.Popover):
                    def __init__(self, **kw):
                        super().__init__(**(kw | {'autohide':False}))
                try:
                    with patch('conversor.Gtk.Popover',new=UngrabbedPopover):
                        state['wheel'] = FormatWheel(parent,[str(image)])
                    state['wheel'].popover.present()
                    GLib.timeout_add(400,check)
                except Exception as error:
                    errors.append(error)
                    finish()
                return False

            def timeout():
                errors.append(AssertionError('O círculo não concluiu a verificação visual.'))
                finish()
                return False

            window.present()
            GLib.timeout_add(400,open_wheel)
            safety = GLib.timeout_add(8000,timeout)
            loop.run()
            if GLib.MainContext.default().find_source_by_id(safety):
                GLib.source_remove(safety)
            if errors:
                raise errors[0]
            self.assertTrue(state.get('checked'))


if __name__ == '__main__':
    unittest.main()
