"""Windows' local OCR API through PyWinRT; no PowerShell policy changes."""
import asyncio
import os
import re


async def _recognize(path, pages):
    import winrt.windows.foundation  # Register async interface projection.
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.storage.streams import InMemoryRandomAccessStream
    from winrt.windows.graphics.imaging import (BitmapDecoder,BitmapTransform,BitmapPixelFormat,
        BitmapAlphaMode,ExifOrientationMode,ColorManagementMode)
    from winrt.windows.media.ocr import OcrEngine
    import winrt.windows.globalization

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError('No supported OCR language')

    async def read_stream(stream):
        decoder = await BitmapDecoder.create_async(stream)
        scale = min(1,2400/max(decoder.pixel_width,decoder.pixel_height))
        transform = BitmapTransform()
        transform.scaled_width = max(1,round(decoder.pixel_width*scale))
        transform.scaled_height = max(1,round(decoder.pixel_height*scale))
        bitmap = await decoder.get_software_bitmap_async(BitmapPixelFormat.BGRA8,
            BitmapAlphaMode.PREMULTIPLIED,transform,ExifOrientationMode.RESPECT_EXIF_ORIENTATION,
            ColorManagementMode.DO_NOT_COLOR_MANAGE)
        try:
            result = await engine.recognize_async(bitmap)
            text='\n'.join(line.text for line in result.lines)
            return re.sub(r'(?<=[\u3400-\u9fff，。：；！？]) +(?=[\u3400-\u9fff，。：；！？])','',text)
        finally:
            bitmap.close()

    file = await StorageFile.get_file_from_path_async(str(path.resolve()))
    if pages:
        from winrt.windows.data.pdf import PdfDocument,PdfPageRenderOptions
        pdf = await PdfDocument.load_from_file_async(file)
        units = []
        for number in pages:
            page = pdf.get_page(number-1)
            stream = InMemoryRandomAccessStream()
            try:
                options=PdfPageRenderOptions();options.destination_width=1800
                await page.render_to_stream_async(stream,options)
                stream.seek(0)
                units.append({'text':await read_stream(stream),'locator':{'page':number,'method':'ocr'}})
            finally:
                stream.close();page.close()
        return units
    stream = await file.open_async(FileAccessMode.READ)
    try:
        return [{'text':await read_stream(stream),'locator':{'image':1,'method':'ocr'}}]
    finally:
        stream.close()


def recognize(path,pages=None):
    if os.name != 'nt':
        raise RuntimeError('Windows OCR is not available')
    return asyncio.run(_recognize(path,pages))
