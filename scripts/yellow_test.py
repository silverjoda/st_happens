import cv2, numpy as np

img = cv2.imread("/Users/azayevtey/SW/st_happens/data/raw_photos/20230909_120741.jpg")
h, w = img.shape[:2]
roi = img[int(h * 0.75) :, :]
b, g, r = roi[:, :, 0].astype(float), roi[:, :, 1].astype(float), roi[:, :, 2].astype(float)
ypix = roi[(r > 130) & (g > 110) & (b < 100)]
print(len(ypix), "yellow pixels found")
