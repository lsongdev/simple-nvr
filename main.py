#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import cv2
import threading
import time
import yaml
import queue
import logging
import numpy as np
from datetime import datetime
from onvif import ONVIFCamera
from flask import Flask, Response, render_template, send_file, request

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cameras = {}

def create_onvif_stream_uri(config) -> str:
    """Create RTSP stream URI from ONVIF camera configuration"""
    user = config["user"]
    password = config["password"]
    cam = ONVIFCamera(
        config["host"], 
        config["port"], 
        user, 
        password
    )
    media = cam.create_media_service()
    profiles = media.GetProfiles()
    token = profiles[0].token
    stream_setup = {
        'Stream': 'RTP-Unicast',
        'Transport': {
            'Protocol': 'RTSP'
        }
    }
    uri = media.GetStreamUri({
        'ProfileToken': token,
        'StreamSetup': stream_setup
    })
    
    rtsp_uri = uri.Uri
    if not rtsp_uri.startswith("rtsp://"):
        return rtsp_uri
    
    auth_uri = f"rtsp://{user}:{password}@{rtsp_uri[7:]}"
    return auth_uri

def create_video_capture(config) -> cv2.VideoCapture:
    """Create video capture from camera configuration"""
    if config["type"] == "onvif":
        config["source"] = create_onvif_stream_uri(config)
    return cv2.VideoCapture(config["source"])


def capture_frames(camera_id: str):
    """Capture frames from camera and put them into queue"""
    logger.info(f"Started capturing frames for camera {camera_id}")
    retry_count = 0
    camera = cameras.get(camera_id)
    while camera["is_running"]:
        success, frame = camera["capture"].read()
        if not success:
            retry_count += 1
            if retry_count >= camera.get("max_retries", 5):
                logger.error(f"Camera {camera_id} exceeded retry limit")
                break
            time.sleep(camera.get("retry_interval", 1))
            continue

        retry_count = 0
        if "rotate" in camera:
            frame = cv2.rotate(frame, camera["rotate"])
        try:
            camera["frame_queue"].put(frame, timeout=1)
        except queue.Full:
            continue
        except Exception as e:
            logger.error(f"Error putting frame into queue: {str(e)}")
            break

    logger.info(f"Stopped capturing frames for camera {camera_id}")
    # camera["capture"].release()


def create_frame_generator(camera):
    """Generate MJPEG frames for streaming"""
    while camera["is_running"]:
        try:
            frame = camera["frame_queue"].get(timeout=1)
            success, jpeg = cv2.imencode(".jpg", frame)
            if success:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                )
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error generating stream frame: {str(e)}")
            break


def create_video_writer(
    frame: np.ndarray, output_path: str, fps: float = 20.0
) -> cv2.VideoWriter:
    """Create video writer for recording"""
    height, width = frame.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    return cv2.VideoWriter(output_path, fourcc, fps, (width, height))


def record_video(camera_id):
    """Record video from frame queue"""
    logger.info(f"Started recording for camera {camera_id}")
    writer = None
    start_time = 0
    camera = cameras.get(camera_id)
    while camera["is_running"]:
        try:
            frame = camera["frame_queue"].get(timeout=5)
            if time.time() - start_time >= camera.get("max_duration", 3600):
                if writer:
                    writer.release()
                os.makedirs(camera["output_dir"], exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(
                    camera["output_dir"], f"{camera_id}_{timestamp}.avi"
                )
                writer = create_video_writer(frame, filename)
                start_time = time.time()
                logger.info(f"Created new video file: {filename}")
                continue
            writer.write(frame)
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error writing video frame: {str(e)}")
            break

    if writer:
        writer.release()
    logger.info(f"Stopped recording for camera {camera_id}")


def create_camera(camera):
    """Create camera system from configuration"""
    camera["capture"] = create_video_capture(camera)
    camera["frame_queue"] = queue.Queue(maxsize=30)
    camera["max_duration"] = 3600
    camera["capture_thread"] = None
    camera["record_thread"] = None
    camera["is_running"] = None
    camera["output_dir"] = os.path.join("recordings", camera["id"])
    return camera


def start_camera(camera):
    if camera["is_running"]:
        logger.warning(f"Camera {camera['id']} is already running")
        return

    camera["is_running"] = True
    camera["capture_thread"] = threading.Thread(
        target=capture_frames, args=(camera["id"],), daemon=True
    )
    camera["capture_thread"].start()
    camera["record_thread"] = threading.Thread(
        target=record_video, args=(camera["id"],), daemon=True
    )
    camera["record_thread"].start()


def stop_camera(camera):
    camera["is_running"] = False


# Flask application
app = Flask(__name__)


@app.route("/")
@app.route("/cameras")
def index():
    return render_template("index.html", cameras=cameras)


@app.route("/cameras/<camera_id>")
def camera_view(camera_id):
    if camera_id not in cameras:
        return "Camera not found", 404

    video_files = []
    if os.path.exists(camera["output_dir"]):
        files = os.listdir(camera["output_dir"])
        video_files = [
            f for f in files if f.startswith(f"{camera_id}_") and f.endswith(".avi")
        ]
        video_files.sort(reverse=True)
    return render_template(
        "camera.html", camera=cameras.get(camera_id), video_files=video_files
    )


@app.route("/cameras/<camera_id>/preview")
def camera_preview(camera_id):
    """Video streaming route"""
    if camera_id not in cameras:
        return "Camera not found", 404
    return Response(
        create_frame_generator(cameras.get(camera_id)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/cameras/<camera_id>/start")
def start_camera_route(camera_id: str):
    """Start camera route"""
    if camera_id not in cameras:
        return "Camera not found", 404
    start_camera(cameras[camera_id])
    return "Camera started", 200


@app.route("/cameras/<camera_id>/stop")
def stop_camera_route(camera_id: str):
    """Stop camera route"""
    if camera_id not in cameras:
        return "Camera not found", 404
    stop_camera(cameras[camera_id])
    return "Camera stopped", 200


@app.route("/cameras/<camera_id>/files/<filename>")
def file_route(camera_id, filename):
    if camera_id not in cameras:
        return "Camera not found", 404

    camera = cameras.get(camera_id)
    video_path = os.path.join(camera["output_dir"], filename)
    if not os.path.exists(video_path):
        return "Video not found", 404
    return send_file(
        video_path,
        mimetype="video/x-msvideo",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/cameras/<camera_id>/ptz")
def ptz_control(camera_id):
   if camera_id not in cameras:
       return "Camera not found", 404
       
   camera = cameras[camera_id]
   action = request.args.get('action')
   
   cam = ONVIFCamera(camera["host"], camera["port"], camera["user"], camera["password"])
   ptz = cam.create_ptz_service()
   media = cam.create_media_service()
   
   profile = media.GetProfiles()[0]
   token = profile.token
   
   # 获取速度空间
   req = ptz.create_type('GetConfigurationOptions')
   req.ConfigurationToken = profile.PTZConfiguration.token
   ptz_config = ptz.GetConfigurationOptions(req)

   # 创建移动请求
   req = ptz.create_type('ContinuousMove')
   req.ProfileToken = token

   if action == 'left':
       req.Velocity = {'PanTilt': {'x': -0.5, 'y': 0}, 'Zoom': {'x': 0}}
   elif action == 'right':
       req.Velocity = {'PanTilt': {'x': 0.5, 'y': 0}, 'Zoom': {'x': 0}}
   elif action == 'up':
       req.Velocity = {'PanTilt': {'x': 0, 'y': 0.5}, 'Zoom': {'x': 0}}
   elif action == 'down':
       req.Velocity = {'PanTilt': {'x': 0, 'y': -0.5}, 'Zoom': {'x': 0}}
   elif action == 'stop':
       ptz.Stop({'ProfileToken': token})
       return "PTZ stopped"
   
   ptz.ContinuousMove(req)
   time.sleep(0.5)
   ptz.Stop({'ProfileToken': token})
   
   return "PTZ moved"

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    config = load_config()
    # Initialize camera systems
    for camera_config in config["cameras"]:
        camera = create_camera(camera_config)
        cameras[camera["id"]] = camera
        start_camera(camera)

    # Start Flask application
    app.run(
        host=config.get("host", config.get("host", "0.0.0.0")),
        port=config.get("port", config.get("port", 5000)),
        threaded=True,
    )
