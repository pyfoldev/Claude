import numpy as np, cv2, onnxruntime as ort, mediapipe as mp, itertools
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision
fc = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'); ec = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
sess = ort.InferenceSession('models/mfn/mobile_facenet-onnx-float/mobile_facenet_onnx/mobile_facenet.onnx', providers=['CPUExecutionProvider'])
# эталон ArcFace для 112x112: глаза и центр рта (центр рта = среднее двух уголков)
TPL = np.float32([[38.2946, 51.6963], [73.5318, 51.5014], [(41.5493 + 70.7299) / 2, (92.3655 + 92.2041) / 2]])
def faces(path):
    bgr = cv2.imread(path); g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY); out = []
    for (x, y, w, h) in sorted(fc.detectMultiScale(g, 1.1, 6, minSize=(60, 60)), key=lambda r: -r[2]):
        eyes = sorted(ec.detectMultiScale(g[y:y + h * 6 // 10, x:x + w], 1.1, 5, minSize=(w // 8, w // 8)), key=lambda r: r[0])
        if len(eyes) < 2: continue
        e1, e2 = eyes[0], eyes[-1]
        pts = np.float32([[x + e1[0] + e1[2] / 2, y + e1[1] + e1[3] / 2], [x + e2[0] + e2[2] / 2, y + e2[1] + e2[3] / 2], [x + w / 2, y + h * 0.80]])
        M, _ = cv2.estimateAffinePartial2D(pts, TPL, method=cv2.LMEDS)
        out.append(cv2.warpAffine(bgr, M, (112, 112), borderValue=(0, 0, 0)))
    return out
def emb(crop):
    x = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255
    e = sess.run(None, {'img1': x, 'img2': x})[0][0]; return e / np.linalg.norm(e)
E = {}
for f in ['obama.jpg', 'obama2.jpg', 'obama_small.jpg', 'biden.jpg', 'alex-lacamoire.png', 'lin-manuel-miranda.png']:
    fs = faces('faces/' + f); print(f, 'лиц найдено:', len(fs))
    if fs: E[f] = emb(fs[0]); cv2.imwrite(f'faces/crop_{f}.png', fs[0])
fs = faces('faces/two_people.jpg'); print('two_people лиц:', len(fs))
for i, c in enumerate(fs[:2]): E[f'two_{i}'] = emb(c)
print('\nСходство (косинус):')
for a, b in itertools.combinations(E, 2): print(f'  {a:24s} {b:24s} {float(E[a] @ E[b]):.2f}', '← один человек' if {a, b} <= {'obama.jpg', 'obama2.jpg', 'obama_small.jpg'} else '')
