# Simple NVR

A lightweight, web-based Network Video Recorder (NVR) system built with Python, Flask, and OpenCV. Simple NVR supports local, RTSP, and ONVIF cameras, providing live streaming, recording, and PTZ (Pan-Tilt-Zoom) control via a modern web interface.

## Features

- **Multi-camera support**: Add local, RTSP, or ONVIF cameras via configuration.
- **Live streaming**: View real-time MJPEG streams from all cameras in your browser.
- **Recording**: Automatically records video to disk, splitting files by duration.
- **PTZ control**: Control ONVIF camera pan, tilt, and zoom from the web UI.
- **Playback & download**: Browse and download recorded video files per camera.
- **Modern web UI**: Clean, responsive interface for easy camera management.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Edit the `config.yaml` file to define your cameras and server settings. Example:

```yaml
host: 0.0.0.0
port: 8000
output_dir: recordings

cameras:
  - id: cam1
    type: local
    source: 0

  - id: cam2
    type: rtsp
    source: rtsp://user:password@192.168.1.100/stream1
    rotate: 0

  - id: cam3
    type: onvif
    host: 192.168.1.101
    port: 80
    user: admin
    password: yourpassword
    rotate: 1
```

- `type`: `local`, `rtsp`, or `onvif`
- `source`: Camera index (for local), RTSP URL, or ONVIF details
- `rotate`: (optional) 0, 1, or 2 (number of 90-degree rotations)

## Usage

Start the NVR server:

```bash
python main.py
```

The web interface will be available at `http://<host>:<port>/` (default: `http://localhost:8000/`).

## Web Interface

- **Index page**: Lists all cameras, their status, and live preview thumbnails.
- **Camera page**: View live stream, control PTZ (if supported), and browse/download recordings.
- **Start/Stop**: Start or stop individual camera streams and recordings.

### PTZ Controls (ONVIF cameras)
- Use the arrow buttons to move the camera left, right, up, or down.
- Press the stop button to halt movement.

## Recordings

- Video files are saved in the `recordings/<camera_id>/` directory as `.avi` files.
- Files are split by duration (default: 1 hour per file).

## Notes

- `.avi` video files and the `recordings/` directory are ignored by git (see `.gitignore`).
- For ONVIF cameras, ensure the camera supports ONVIF and the credentials are correct.
- The web UI uses AJAX for PTZ and camera control actions.

## License

This project is licensed under the [GPLv3 license and specific limitations](https://github.com/lsongdev/.github/blob/main/LICENSE.md).