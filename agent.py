# agent.py
# Designed to run on a Raspberry Pi 3
# usage of Sense Hat and statsd optional
import logging
logging.basicConfig(format='%(asctime)s %(name)s %(levelname)s %(message)s', level=logging.INFO)
log = logging.getLogger('catscanface-agent')
import datetime
import argparse
import time
import os

from picamera.array import PiRGBArray
from picamera import PiCamera
import cv2
import boto3


def annotate_frame(frame, contour):
    timestamp = datetime.datetime.now()
    ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")
    (x, y, w, h) = cv2.boundingRect(contour)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), 2)
    cv2.putText(frame, ts, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
    return frame


def start(args):
    camera = PiCamera()
    camera.resolution = args.resolution
    camera.framerate = args.fps
    hat = None
    statsd = None
    log.info("Warming up camera")
    time.sleep(5)

    if args.enable_sensehat:
        from sense_hat import SenseHat
        hat = SenseHat()
        hat.clear()

    if args.enable_statsd:
        from datadog import statsd

    loop(args, camera, hat, statsd)


def loop(args, camera, hat, statsd):
    avg = None
    raw_capture = PiRGBArray(camera, size=args.resolution)
    log.info("Starting capture")
    s3 = None
    if args.enable_s3:
        s3 = boto3.client('s3')

    for f in camera.capture_continuous(raw_capture, format="bgr", use_video_port=True):
        frame = f.array

        # resize, grayscale & blur out noise
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # if the average frame is None, initialize it
        if avg is None:
            log.info("Initialising average frame")
            avg = gray.copy().astype("float")
            raw_capture.truncate(0)
            continue

        # accumulate the weighted average between the current frame and
        # previous frames, then compute the difference between the current
        # frame and running average
        cv2.accumulateWeighted(gray, avg, 0.5)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

        # threshold the delta image, dilate the thresholded image to fill
        # in holes, then find contours on thresholded image
        thresh = cv2.threshold(frame_delta, args.delta_threshold, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        (contours, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion = False
        for c in contours:
            # if the contour is too small, ignore it
            if cv2.contourArea(c) < args.min_area:
                continue

            motion = True
            log.info("Motion detected")

            # draw the text and timestamp on the frame
            if args.enable_annotate:
                frame = annotate_frame(frame, c)

            if args.enable_sensehat:
                hat.show_letter('X', back_colour=[255, 20, 50])

            if args.enable_statsd:
                statsd.increment('camera.motion_detected')

        if motion:
            img_name = datetime.datetime.utcnow().strftime('%Y-%m-%d_%H_%M_%S.%f') + '.jpg'
            img_path = '{}/{}'.format(args.image_path, img_name)
            cv2.imwrite(img_path, frame)

            # todo enqueue upload so it doesn't block main loop
            if args.enable_s3:
                with open(img_path, 'rb') as data:
                    log.debug('Uploading to s3://{}/{}{}...'.format(args.s3_bucket, args.s3_prefix, img_name))
                    s3.upload_fileobj(data, args.s3_bucket, args.s3_prefix + img_name)
                    log.debug('Uploaded')

        raw_capture.truncate(0)
        motion = False
        if args.enable_sensehat:
            hat.clear()


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


def parse_res(v):
    x, y = v.lower().split('x')
    return int(x), int(y)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Motion detect and upload frames to S3')
    parser.add_argument('--resolution', help='e.g 640x480', default=parse_res(os.environ.get('resolution', '640x480')))
    parser.add_argument('--fps', help='Framerate e.g: 18', default=int(os.environ.get('fps', '18')))
    parser.add_argument('--delta-threshold', default=int(os.environ.get('delta_threshold', 5)))
    parser.add_argument('--min-area', default=int(os.environ.get('min_area', 5000)))
    parser.add_argument('--enable-sensehat', help='Use Sense Hat display', action='store_true', default=str2bool(os.environ.get('enable_sensehat', '0')))
    parser.add_argument('--enable-statsd', help='Send metrics', action='store_true', default=str2bool(os.environ.get('enable_statsd', '0')))
    parser.add_argument('--enable-annotate', help='Draw detected regions to image', action='store_true', default=str2bool(os.environ.get('enable_annotate', '0')))
    parser.add_argument('--image-path', help='Where to save images locally eg /tmp', default=os.environ.get('image_path', '/tmp'))
    parser.add_argument('--enable-s3', help='Enable saving frames to AWS S3', action='store_true', default=os.environ.get('enable_s3', '1'))
    parser.add_argument('--s3-bucket', help='AWS S3 bucket to save frames', default=os.environ.get('s3_bucket', 'timatooth'))
    parser.add_argument('--s3-prefix', help='AWS S3 bucket prefix path e.g cats/', default=os.environ.get('s3_prefix', 'catscanface/motion/'))

    args = parser.parse_args()
    log.debug(args)
    start(args)
