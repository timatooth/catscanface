from __future__ import print_function
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
import os
import os.path
import numpy
import cv2
import boto3

# Config
s3_prefix = 'catscanface/'
s3_bucket = 'timatooth'

cat_cascade = cv2.CascadeClassifier('haarcascade_frontalcatface_extended.xml')
s3_client = boto3.client('s3')

def scan_frame(image_data):
    img_array = numpy.asarray(bytearray(image_data), dtype=numpy.uint8)
    frame = cv2.imdecode(img_array, 0)
    cat_faces = cat_cascade.detectMultiScale(frame, 1.3, 5)
    # Draw rectangle onto region where cat face is found
    cat_detected = False
    for (x, y, w, h) in cat_faces:
        cat_detected = True
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        logger.info("Found cat")

    if cat_detected:
        _, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes()


def get_image(object_key):
    response = s3_client.get_object(Bucket=s3_bucket, Key=object_key)
    image_bytes = response['Body'].read()
    logger.info('Got {} bytes'.format(len(image_bytes)))
    return image_bytes


def lambda_handler(event, context):
    object_key = event['Records'][0]['s3']['object']['key']
    image_bytes = get_image(object_key)
    cat_image = scan_frame(image_bytes)
    if cat_image is not None:
        key = s3_prefix + 'detections/' + os.path.basename(object_key)
        logger.info('Saving cat detection image: {}'.format(key))
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=key,
            Body=cat_image
        )
