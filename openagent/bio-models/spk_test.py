import os, json, subprocess, urllib.request, numpy as np, onnxruntime as ort, sys, itertools
KEY = os.environ['DEEPGRAM_API_KEY']
voices = ['thalia','andromeda','helena','apollo','arcas','aries','asteria','athena','atlas','aurora','callista','cora','draco','hera','hermes','janus','jupiter','luna','mars','orion']
texts = ["Hello, this is my voice and I would like to unlock the assistant now.", "The weather today is quite nice, so I might go for a walk in the park.", "Please remind me to call my sister tomorrow morning at nine thirty."]
os.makedirs('spk', exist_ok=True)
def tts(v, i):
    p = f'spk/{v}_{i}.pcm'
    if not os.path.exists(p):
        r = urllib.request.Request(f'https://api.deepgram.com/v1/speak?model=aura-2-{v}-en&encoding=linear16&sample_rate=16000&container=none', data=json.dumps({'text': texts[i]}).encode(), headers={'Authorization': f'Token {KEY}', 'Content-Type': 'application/json'})
        try: open(p, 'wb').write(urllib.request.urlopen(r, timeout=60).read())
        except Exception as e: return None
    return np.frombuffer(open(p, 'rb').read(), dtype='<i2').astype(np.float32) / 32768
for name in ['b0', 'b2']:
    s = ort.InferenceSession(f'redimnet2_{name}.onnx', providers=['CPUExecutionProvider'])
    emb = {}
    for v in voices:
        for i in range(3):
            w = tts(v, i)
            if w is None or len(w) < 16000: continue
            e = s.run(None, {'wave': w[None]})[0][0]; emb[(v, i)] = e / np.linalg.norm(e)
    keys = list(emb); same, diff = [], []
    for a, b in itertools.combinations(keys, 2):
        c = float(emb[a] @ emb[b]); (same if a[0] == b[0] else diff).append(c)
    same, diff = np.array(same), np.array(diff)
    print(f'{name}: голосов {len({k[0] for k in keys})}; тот же голос: мин {same.min():.2f} медиана {np.median(same):.2f} | разные: медиана {np.median(diff):.2f} макс {diff.max():.2f} p99 {np.percentile(diff, 99):.2f}')
    for thr in (0.5, 0.6, 0.7, 0.8): print(f'   порог {thr}: свой принят {np.mean(same >= thr):.0%}, чужой принят {np.mean(diff >= thr):.1%}')
