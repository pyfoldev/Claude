import sys, time, torch, numpy as np, os
sys.path.insert(0, 'redimnet2')
name = sys.argv[1]
m = torch.hub.load('redimnet2', 'redimnet2', model_name=name, train_type='lm', pretrained=True, source='local')
m.eval()
x = torch.randn(1, 48000) * 0.1
with torch.no_grad(): ref = m(x)
print(name, 'emb', tuple(ref.shape), 'params', sum(p.numel() for p in m.parameters()) / 1e6, 'M')
out = f'redimnet2_{name}.onnx'
torch.onnx.export(m, (x,), out, input_names=['wave'], output_names=['emb'], opset_version=17, dynamic_axes={'wave': {1: 'n'}}, dynamo=False)
print('onnx size', os.path.getsize(out) / 1e6, 'MB')
import onnxruntime as ort
s = ort.InferenceSession(out, providers=['CPUExecutionProvider'])
for n in (32000, 48000, 80000):
    xx = torch.randn(1, n) * 0.1
    with torch.no_grad(): r = m(xx).numpy()
    t0 = time.time(); o = s.run(None, {'wave': xx.numpy()})[0]; dt = time.time() - t0
    cos = float((r * o).sum() / (np.linalg.norm(r) * np.linalg.norm(o)))
    print(f'  {n/16000:.1f}s: ORT {dt*1000:.0f} мс, cos(torch,onnx)={cos:.5f}, max|diff|={np.abs(r-o).max():.2e}')
