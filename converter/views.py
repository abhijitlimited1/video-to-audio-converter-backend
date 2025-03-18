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
from django.conf import settings

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
                
                # Enhanced validation for mobile uploads
                allowed_mime_types = [
                    'video/mp4', 'video/quicktime', 
                    'video/x-msvideo', 'video/mpeg', 'video/webm'
                ]
                allowed_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')
                
                # Check both MIME type and extension
                if (file.content_type not in allowed_mime_types or 
                    not file.name.lower().endswith(allowed_extensions)):
                    return Response({'error': 'Unsupported file format'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

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

            # URL handling with YouTube fixes
            elif request.data.get('url'):
                url = request.data['url'].strip()
                if not url.startswith(('http://', 'https://')):
                    return Response({'error': 'Invalid URL format'}, 
                                  status=status.HTTP_400_BAD_REQUEST)

                try:
                    cookies_path = os.path.join(settings.BASE_DIR, 'cookies.txt')
                    proxy = os.getenv('YT_PROXY', '')  # Set proxy via environment variables

                    cmd = [
                        'yt-dlp',
                        '-x',
                        '--audio-format', 'mp3',
                        '--audio-quality', '192k',
                        '-o', '-',
                        '--quiet',
                        '--force-ipv4',
                        '--throttled-rate', '100K',
                        '--socket-timeout', '30',
                        '--source-address', '0.0.0.0',
                        '--add-header', 'User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    ]

                    if os.path.exists(cookies_path):
                        cmd.extend(['--cookies', cookies_path])
                    if proxy:
                        cmd.extend(['--proxy', proxy])

                    cmd.append(url)

                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=300
                    )
                    output_buffer.write(result.stdout)
                except subprocess.TimeoutExpired:
                    logger.error("YouTube download timed out")
                    return Response({'error': 'Download timed out'}, 
                                  status=status.HTTP_408_REQUEST_TIMEOUT)
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr.decode()
                    logger.error(f"yt-dlp error: {error_msg}")
                    
                    # User-friendly error messages
                    if "429" in error_msg:
                        return Response({'error': 'YouTube rate limit exceeded - try again later'},
                                        status=status.HTTP_429_TOO_MANY_REQUESTS)
                    elif "Sign in to confirm" in error_msg:
                        return Response({'error': 'YouTube requires verification - try different video'},
                                        status=status.HTTP_403_FORBIDDEN)
                    else:
                        return Response({'error': f'Download failed: {error_msg}'},
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