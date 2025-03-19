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
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class ConvertVideo(APIView):
    def post(self, request):
        output_buffer = io.BytesIO()
        
        try:
            if not request.FILES.get('file') and not request.data.get('url'):
                return Response({'error': 'Please provide input'}, 
                              status=status.HTTP_400_BAD_REQUEST)

            # File upload handling with mobile-compatible settings
            if request.FILES.get('file'):
                file = request.FILES['file']
                allowed_mime_types = [
                    'video/mp4', 'video/quicktime', 
                    'video/x-msvideo', 'video/mpeg', 'video/webm'
                ]
                allowed_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')
                
                if (file.content_type not in allowed_mime_types or 
                    not file.name.lower().endswith(allowed_extensions)):
                    return Response({'error': 'Unsupported file format'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                if file.size > 500 * 1024 * 1024:
                    return Response({'error': 'File too large'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    input_data = file.read()
                    # Mobile-optimized conversion parameters
                    process = (
                        ffmpeg
                        .input('pipe:0')
                        .output(
                            'pipe:1',
                            format='mp3',
                            acodec='libmp3lame',
                            audio_bitrate='192k',
                            ar='44100',  # Force standard sample rate
                            ac='2',      # Force stereo
                            write_xing=0,
                            **{
                                'id3v2_version': '3',
                                'metadata:s:a:0': 'title=Converted Audio',
                                'metadata:s:a:0': 'artist=Audio Converter',
                            }
                        )
                        .overwrite_output()
                        .run_async(pipe_stdin=True, pipe_stdout=True, quiet=True)
                    )

                    process.communicate(input=input_data)
                    output_buffer.write(process.stdout.read())
                    
                except ffmpeg.Error as e:
                    logger.error(f"FFmpeg error: {e.stderr.decode()}")
                    return Response({'error': f'Conversion error: {e.stderr.decode()}'},
                                  status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # URL handling with mobile-specific optimizations
            elif request.data.get('url'):
                url = request.data['url'].strip()
                if not url.startswith(('http://', 'https://')):
                    return Response({'error': 'Invalid URL format'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    cmd = [
                        'yt-dlp',
                        '-x',
                        '--audio-format', 'mp3',
                        '--audio-quality', '192k',
                        '--embed-thumbnail',
                        '--add-metadata',
                        '--postprocessor-args', 'ffmpeg:-id3v2_version 3 -ar 44100 -ac 2',
                        '-o', '-',
                        '--quiet',
                        '--force-ipv4',
                        '--throttled-rate', '50K',
                        url
                    ]

                    cookies_path = os.path.join(settings.BASE_DIR, 'cookies.txt')
                    if os.path.exists(cookies_path):
                        cmd.extend(['--cookies', cookies_path])

                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=300
                    )
                    output_buffer.write(result.stdout)
                    
                except subprocess.TimeoutExpired:
                    return Response({'error': 'Download timed out - try smaller videos'}, 
                                  status=status.HTTP_408_REQUEST_TIMEOUT)
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr.decode()
                    logger.error(f"yt-dlp error: {error_msg}")
                    return Response({
                        'error': 'YouTube conversion failed',
                        'solution': 'Try downloading the video and uploading it directly'
                    }, status=status.HTTP_400_BAD_REQUEST)

            output_buffer.seek(0)
            
            # Create response with mobile-friendly headers
            response = FileResponse(
                output_buffer,
                content_type='audio/mpeg',
                as_attachment=True,
                filename=f"audio_{uuid.uuid4().hex}.mp3"
            )
            response['Content-Length'] = str(output_buffer.getbuffer().nbytes)
            response['Accept-Ranges'] = 'bytes'
            response['Cache-Control'] = 'no-store, max-age=0'
            
            return response

        except Exception as e:
            logger.error(f"General error: {str(e)}", exc_info=True)
            return Response({'error': 'Conversion failed'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

    def validate_mp3(file_bytes):
        try:
            audio = AudioSegment.from_file(io.BytesIO(file_bytes), format="mp3")
            return True
        except:
             return False