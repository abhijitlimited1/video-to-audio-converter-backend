import os
import uuid
import ffmpeg
import logging
import io
import subprocess
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse
from django.conf import settings

logger = logging.getLogger(__name__)

class ConvertVideo(APIView):
    def post(self, request):
        output_buffer = io.BytesIO()
        
        try:
            if not request.FILES.get('file') and not request.data.get('url'):
                return Response({'error': 'Please provide input'}, 
                              status=status.HTTP_400_BAD_REQUEST)

            # File upload handling
            if request.FILES.get('file'):
                file = request.FILES['file']
                allowed_types = [
                    'video/mp4', 'video/quicktime', 
                    'video/x-msvideo', 'video/mpeg', 'video/webm'
                ]
                
                if file.content_type not in allowed_types:
                    return Response({'error': 'Unsupported file format'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                if file.size > 500 * 1024 * 1024:
                    return Response({'error': 'File too large'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    input_data = file.read()
                    process = (
                        ffmpeg
                        .input('pipe:0')
                        .output(
                            'pipe:1',
                            format='mp3',
                            acodec='libmp3lame',
                            audio_bitrate='192k',
                            ar='44100',
                            ac='2',
                            write_xing=0,
                            **{'id3v2_version': '3'}
                        )
                        .overwrite_output()
                        .run_async(pipe_stdin=True, pipe_stdout=True, quiet=True)
                    )
                    process.stdin.write(input_data)
                    process.stdin.close()
                    output_buffer.write(process.stdout.read())
                    process.wait()
                    
                except Exception as e:
                    logger.error(f"FFmpeg error: {str(e)}")
                    return Response({'error': 'File conversion failed'}, 
                                  status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # URL handling
            elif request.data.get('url'):
                url = request.data['url'].strip()
                if not url.startswith(('http://', 'https://')):
                    return Response({'error': 'Invalid URL format', 'solution': 'Try file upload instead'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    cmd = [
                        'yt-dlp',
                        '-x',
                        '--audio-format', 'mp3',
                        '--audio-quality', '192k',
                        '--postprocessor-args', 'ffmpeg:-id3v2_version 3 -ar 44100 -ac 2',
                        '-o', '-',
                        '--quiet',
                        url
                    ]

                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=300
                    )

                    if result.returncode != 0:
                        raise subprocess.CalledProcessError(
                            result.returncode, cmd, result.stdout, result.stderr
                        )

                    output_buffer.write(result.stdout)
                    
                except subprocess.TimeoutExpired:
                    return Response({
                        'error': 'URL processing timed out',
                        'solution': 'Try uploading the file directly'
                    }, status=status.HTTP_408_REQUEST_TIMEOUT)
                except Exception as e:
                    return Response({
                        'error': 'URL conversion failed',
                        'solution': 'Download the video and upload it here'
                    }, status=status.HTTP_400_BAD_REQUEST)

            output_buffer.seek(0)
            
            response = FileResponse(
                output_buffer,
                content_type='audio/mpeg',
                as_attachment=True,
                filename=f"audio_{uuid.uuid4().hex}.mp3"
            )
            response['Content-Length'] = output_buffer.getbuffer().nbytes
            response['Cache-Control'] = 'no-store'
            
            return response

        except Exception as e:
            logger.error(f"Conversion error: {str(e)}")
            return Response({'error': 'Conversion failed'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)