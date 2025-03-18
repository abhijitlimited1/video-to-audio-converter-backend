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

            # URL handling with free tier optimizations
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
                        '-o', '-',
                        '--quiet',
                        '--force-ipv4',
                        '--throttled-rate', '50K',
                        '--sleep-interval', '30',
                        '--referer', 'https://www.google.com/',
                        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        url
                    ]

                    # Add cookies if available
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
                    
                    if "429" in error_msg:
                        return Response({
                            'error': 'YouTube limit reached 😢 Try again later',
                            'workaround': 'Download video first, then upload file'
                        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
                    elif "Sign in to confirm" in error_msg:
                        return Response({
                            'error': 'Age-restricted content',
                            'solution': 'Use file upload instead'
                        }, status=status.HTTP_403_FORBIDDEN)
                    else:
                        return Response({
                            'error': 'URL conversion failed',
                            'alternative': 'Try uploading the video file'
                        }, status=status.HTTP_400_BAD_REQUEST)

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