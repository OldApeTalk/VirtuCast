"""
VideoCraft Bridge
Integration layer for reusing VideoCraft TTS and subtitle tools
"""

import sys
from pathlib import Path
from typing import Optional, List


class VideoCraftBridge:
    """
    Bridge to VideoCraft functionality
    Reuses TTS, subtitle generation, and video processing tools
    """
    
    def __init__(self, videocraft_path: Optional[str] = None):
        """
        Initialize VideoCraft bridge
        
        Args:
            videocraft_path: Path to VideoCraft project (auto-detected if None)
        """
        self.videocraft_path = self._find_videocraft_path(videocraft_path)
        self._add_to_path()
        self._import_modules()
    
    def _find_videocraft_path(self, provided_path: Optional[str]) -> Path:
        """Find VideoCraft installation"""
        if provided_path:
            return Path(provided_path)
        
        # Try to find VideoCraft relative to current project
        current_dir = Path(__file__).parent.parent
        possible_paths = [
            current_dir.parent / "VideoCraft" / "src",
            Path("d:/My_Prjs/VideoCraft/src"),
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        raise FileNotFoundError("VideoCraft not found. Please specify path.")
    
    def _add_to_path(self):
        """Add VideoCraft to Python path"""
        if str(self.videocraft_path) not in sys.path:
            sys.path.insert(0, str(self.videocraft_path))
    
    def _import_modules(self):
        """Import VideoCraft modules"""
        try:
            # Import as needed - examples:
            # from text2Video import generate_tts
            # from SrtTools import generate_srt
            print(f"[VideoCraftBridge] Loaded from: {self.videocraft_path}")
        except ImportError as e:
            print(f"[VideoCraftBridge] Warning: Could not import modules: {e}")
    
    def generate_tts(self, text: str, output_path: str, voice: str = "default") -> str:
        """
        Generate TTS audio using VideoCraft
        
        Args:
            text: Text to convert to speech
            output_path: Output audio file path
            voice: Voice model to use
            
        Returns:
            Path to generated audio file
        """
        # TODO: Integrate with VideoCraft TTS module
        print(f"[VideoCraftBridge] Generating TTS: {len(text)} chars")
        return output_path
    
    def generate_subtitles(self, text: str, audio_path: str, output_path: str) -> str:
        """
        Generate subtitle file
        
        Args:
            text: Subtitle text
            audio_path: Audio file for timing
            output_path: Output SRT file path
            
        Returns:
            Path to generated subtitle file
        """
        # TODO: Integrate with VideoCraft subtitle tools
        print(f"[VideoCraftBridge] Generating subtitles")
        return output_path
    
    def merge_video_subtitle(self, video_path: str, subtitle_path: str, output_path: str) -> str:
        """
        Merge video with subtitles
        
        Args:
            video_path: Input video file
            subtitle_path: SRT subtitle file
            output_path: Output video with burned-in subtitles
            
        Returns:
            Path to output video
        """
        # TODO: Integrate with VideoCraft video tools
        print(f"[VideoCraftBridge] Merging subtitles into video")
        return output_path


# Example usage
if __name__ == "__main__":
    bridge = VideoCraftBridge()
    # bridge.generate_tts("Hello world", "output/test.wav")
