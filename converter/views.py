import os
import uuid
import ffmpeg
import yt_dlp
import logging
import io
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse

logger = logging.getLogger(__name__)

class ConvertVideo(APIView):
    def post(self, request):
        try:
            if not request.FILES.get('file') and not request.data.get('url'):
                return Response({'error': 'Please provide input'}, status=status.HTTP_400_BAD_REQUEST)

            output_buffer = io.BytesIO()
            
            if request.FILES.get('file'):
                file = request.FILES['file']
                if file.size > 500 * 1024 * 1024:
                    return Response({'error': 'File too large'}, status=status.HTTP_400_BAD_REQUEST)

                # Fixed FFmpeg output capture
                out, _ = (
                    ffmpeg
                    .input('pipe:0')
                    .output('pipe:1', format='mp3', audio_bitrate='192k')
                    .overwrite_output()
                    .run(input=file.read(), capture_stdout=True, capture_stderr=True)
                )
                output_buffer.write(out)

            elif request.data.get('url'):
                url = request.data['url']
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': '-',
                    'quiet': True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    audio_data = ydl.process_ie_result(info, download=True)
                    output_buffer.write(audio_data)

            output_buffer.seek(0)
            return FileResponse(
                output_buffer,
                as_attachment=True,
                filename=f"converted_{uuid.uuid4().hex}.mp3",
                content_type='audio/mpeg'
            )

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"YouTube error: {str(e)}")
            return Response({'error': f'YouTube error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error: {e.stderr.decode()}")
            return Response({'error': f'Conversion error: {e.stderr.decode()}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"General error: {str(e)}")
            return Response({'error': 'Conversion failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)