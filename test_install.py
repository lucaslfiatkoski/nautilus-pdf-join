import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class InstallationTests(unittest.TestCase):
    def test_install_update_and_uninstall_in_custom_data_directory(self):
        project = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "user data"
            env = dict(os.environ, XDG_DATA_HOME=str(data))
            destination = data / "nautilus-python/extensions/juntar_pdfs.py"
            for _ in range(2):
                subprocess.run(["sh", str(project / "install.sh")], env=env, cwd=temp,
                               check=True, capture_output=True)
                self.assertEqual(destination.read_bytes(), (project / "juntar_pdfs.py").read_bytes())
                self.assertEqual(destination.with_name('conversor.py').read_bytes(),
                                 (project / 'conversor.py').read_bytes())
                self.assertEqual(destination.with_name('recortar.py').read_bytes(),
                                 (project / 'recortar.py').read_bytes())
            unrelated = destination.with_name("outra_extensao.py")
            unrelated.write_text("preservar")
            for _ in range(2):
                subprocess.run(["sh", str(project / "uninstall.sh")], env=env, cwd=temp,
                               check=True, capture_output=True)
                self.assertFalse(destination.exists())
                self.assertFalse(destination.with_name('conversor.py').exists())
                self.assertFalse(destination.with_name('recortar.py').exists())
                self.assertEqual(unrelated.read_text(), "preservar")


if __name__ == "__main__":
    unittest.main()
