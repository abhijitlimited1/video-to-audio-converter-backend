import os
import uuid
import ffmpeg
import yt_dlp
import logging
import io
import subprocess
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse

logger = logging.getLogger(__name__)

class ConvertVideo(APIView):
    def post(self, request):
        output_buffer = io.BytesIO()
        
        try:
            # Validate input
            if not request.FILES.get('file') and not request.data.get('url'):
                return Response({'error': 'Please provide input'}, 
                              status=status.HTTP_400_BAD_REQUEST)

            # File upload handling
            if request.FILES.get('file'):
                file = request.FILES['file']
                if file.size > 500 * 1024 * 1024:
                    return Response({'error': 'File too large'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    out, _ = (
                        ffmpeg
                        .input('pipe:0')
                        .output('pipe:1', format='mp3', audio_bitrate='192k')
                        .overwrite_output()
                        .run(input=file.read(), capture_stdout=True, capture_stderr=True)
                    )
                    output_buffer.write(out)
                except ffmpeg.Error as e:
                    logger.error(f"FFmpeg error: {e.stderr.decode()}")
                    return Response({'error': f'Conversion error: {e.stderr.decode()}'},
                                  status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # URL handling
            elif request.data.get('url'):
                url = request.data['url'].strip()
                if not url.startswith(('http://', 'https://')):
                    return Response({'error': 'Invalid URL format'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    # Using subprocess for better error handling
                    result = subprocess.run(
                        [
                            'yt-dlp',
                            '-x',  # Extract audio
                            '--audio-format', 'mp3',
                            '--audio-quality', '192k',
                            '-o', '-',  # Output to stdout
                            '--quiet',
                            url
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True
                    )
                    output_buffer.write(result.stdout)
                except subprocess.CalledProcessError as e:
                    logger.error(f"yt-dlp error: {e.stderr.decode()}")
                    return Response({'error': f'Download failed: {e.stderr.decode()}'},
                                  status=status.HTTP_400_BAD_REQUEST)

            # Return response
            output_buffer.seek(0)
            return FileResponse(
                output_buffer,
                as_attachment=True,
                filename=f"converted_{uuid.uuid4().hex}.mp3",
                content_type='audio/mpeg'
            )

        except Exception as e:
            logger.error(f"General error: {str(e)}", exc_info=True)
            return Response({'error': 'Conversion failed'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)