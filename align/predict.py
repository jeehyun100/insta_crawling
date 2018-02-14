import os
import cv2
import numpy as np
import tensorflow as tf
from scipy import misc
import align.detect_face as detect_face
#from facenet_tf.src.common import facenet
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
import datetime
import dlib
from imutils.face_utils import rect_to_bb
import face_recognition
import matplotlib.pyplot as plt


def get_boxes_frame(minsize, pnet, rnet,onet, threshold, factor,  frame, detect_type, margin, image_size, rotation,cropped_size):
    boxes = []
    img_size = np.asarray(frame.shape)[0:2]
    if len(img_size) == 0:
        return frame, boxes
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    bounding_boxes, _ = detect_face.detect_face(frame, minsize, pnet, rnet, onet,
                                                    threshold, factor)

    for bounding_box in bounding_boxes:

        det = np.squeeze(bounding_box[0:4])

        bb = np.zeros(4, dtype=np.int32)
        bb[0] = np.maximum(det[0] - margin / 2, 0)
        bb[1] = np.maximum(det[1] - margin / 2, 0)
        bb[2] = np.minimum(det[2] + margin / 2, img_size[1])
        bb[3] = np.minimum(det[3] + margin / 2, img_size[0])

        if detect_type == 'dlib':
            bb[2] += bb[0]
            bb[3] += bb[1]
        elif detect_type == 'hog' or detect_type == 'cnn':
            bb[1], bb[2], bb[3], bb[0] = bounding_box

        if len(boxes) == 0:
            boxes.append(bb)
        else:
            if boxes[0][2] - boxes[0][0] < bb[2] - bb[0]:
                boxes[0] = bb

    if len(boxes) > 0:
        cropped = frame[boxes[0][1]:boxes[0][3], boxes[0][0]:boxes[0][2], :]
    else:
        cropped = None


    return cropped, boxes


def main():
    # Arguments  #
    filename = '/home/dev/insta_crawling/data/_ddkhan/5.jpg'
    image = cv2.imread(filename, flags=cv2.IMREAD_COLOR)
    config = tf.ConfigProto(device_count={'GPU': 0})
    with tf.Session(config=config) as sess:
        pnet, rnet, onet = detect_face.create_mtcnn(sess, None)
        #frame, self.minsize, self.pnet, self.rnet, self.onet,self.threshold, self.factor
        minsize = 20
        threshold = [0.6, 0.7, 0.7]
        factor = 0.709
        margin = 10
        image_size = 160
        cropped_size = 25  # rotation use
        detect_type = 'mtcnn' # dlib, mtcnn, hog, cnn
        rotation = False
        aligned, boxes = get_boxes_frame(minsize, pnet, rnet,onet, threshold, factor,  image, detect_type, margin, image_size, rotation,cropped_size)
        if aligned != None:
            cv2.imshow("Window", aligned);
        print("success")

if __name__ == "__main__":
    main()
