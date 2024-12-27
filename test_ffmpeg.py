import subprocess
import sys

def test_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        print("FFmpeg is installed and working:")
        print(result.stdout[:200])  # Print first 200 chars of version info
        return True
    except subprocess.CalledProcessError as e:
        print("Error running FFmpeg:", e)
        return False
    except FileNotFoundError:
        print("FFmpeg is not installed")
        return False

if __name__ == "__main__":
    success = test_ffmpeg()
    sys.exit(0 if success else 1)
