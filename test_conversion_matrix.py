"""Verificação opcional dos pares reais, sem contar aliases ou cópias do formato original."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import cairo
import conversor


@unittest.skipUnless(os.environ.get('RUN_CONVERSION_MATRIX') == '1',
                     'Ative RUN_CONVERSION_MATRIX=1 para exercitar todos os pares de mídia.')
class ConversionMatrixTests(unittest.TestCase):
    def test_real_image_audio_and_video_pairs(self):
        image_formats = ('png','jpg','webp','heic','tiff','avif','bmp','gif','ico','jp2','jxl','qoi','tga')
        audio_formats = ('mp3','m4a','wav','flac','ogg','opus','aiff','wma','aac')
        video_formats = ('mp4','mov','mkv','webm','avi','wmv')
        records, failures = [], []
        with tempfile.TemporaryDirectory(prefix='conversoes-matriz-') as temp:
            folder = Path(temp)
            image = folder / 'fonte.png'
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
            context = cairo.Context(surface)
            context.set_source_rgb(.2, .4, .8)
            context.paint()
            surface.write_to_png(str(image))
            images = {'png': image}
            for kind in image_formats:
                if kind != 'png':
                    images[kind] = conversor.convert_files(kind, [image])[0]
            svg = folder / 'fonte.svg'
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
                           '<rect width="32" height="32" fill="blue"/></svg>')
            images['svg'] = svg
            audio = folder / 'tom.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'sine=frequency=440:duration=0.15',str(audio)],check=True)
            audios = {'wav': audio}
            for kind in audio_formats:
                if kind != 'wav':
                    audios[kind] = conversor.convert_files(kind, [audio])[0]
            video = folder / 'filme.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=32x32:d=0.16',
                            '-f','lavfi','-i','sine=duration=0.16','-shortest',
                            '-c:v','libx264','-c:a','aac',str(video)],check=True)
            videos = {'mp4': video}
            for kind in video_formats:
                if kind != 'mp4':
                    videos[kind] = conversor.convert_files(kind, [video])[0]
            groups = [('imagem',images,(*image_formats,'pdf')),
                      ('áudio',audios,audio_formats),
                      ('vídeo',videos,(*video_formats,'gif',*audio_formats))]
            for category, sources, targets in groups:
                before = len(records)
                for source_format, source in sources.items():
                    for target in targets:
                        if source_format == target:
                            continue
                        try:
                            output = conversor.convert_files(target,[source])[0]
                            if target == 'pdf':
                                command = ['pdfinfo',str(output)]
                            elif category == 'imagem':
                                command = ['magick','identify',str(output)]
                            else:
                                command = ['ffprobe','-v','error','-show_entries',
                                           'stream=codec_type',str(output)]
                            subprocess.run(command,check=True,capture_output=True,timeout=30)
                            records.append({'categoria':category,'origem':source_format,'destino':target})
                        except Exception as error:
                            failures.append({'origem':source_format,'destino':target,'erro':str(error)})
                print(f'{category}: {len(records)-before} pares verificados',flush=True)
        report = {'verificadas':len(records),'pares':records,'falhas':failures}
        report_path = os.environ.get('CONVERSION_MATRIX_REPORT')
        if report_path:
            Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        self.assertFalse(failures, json.dumps(failures,ensure_ascii=False,indent=2))
        self.assertGreaterEqual(len(records),200)


if __name__ == '__main__':
    unittest.main()
