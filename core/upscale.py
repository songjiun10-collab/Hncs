"""Real-ESRGAN(RRDBNet) 기반 AI 업스케일 - PyTorch/ONNX Runtime 둘 다 지원.

`realesrgan`/`basicsr`(공식 pip 패키지)는 의존하지 않는다 - `basicsr`
1.4.2(마지막 PyPI 릴리스, 사실상 유지보수 종료)가 현재 torchvision과
호환 안 됨(`torchvision.transforms.functional_tensor`가 최근
torchvision에서 제거돼 import 자체가 깨짐, 2026-08 실측 확인). 학습용
데이터로더/레지스트리 같은 무거운 부속 없이 추론에 필요한 RRDBNet
아키텍처(`ResidualDenseBlock`/`RRDB`/`RRDBNet`, ESRGAN 논문 구조)와
타일 추론 로직만 그 패키지 소스에서 그대로 옮겨왔다(BSD-3-Clause,
xinntao/Real-ESRGAN) - torch(+ ONNX 변환 1회)와 onnxruntime만 의존.

가중치는 xinntao 공식 GitHub Release(1차 소스, 서드파티 변환본 아님)의
`RealESRGAN_x{2,4}plus.pth`를 받는다. PyTorch 엔진은 그 파일을 바로
쓰고, ONNX 엔진은 같은 파일을 `torch.onnx.export()`로 최초 1회만
변환해서 `models/upscale/`에 캐시해둔다(이후 추론은 onnxruntime만
필요 - torch는 그 변환 1회에만 관여).

100MP급 원본을 4배로 통째로 돌리면 16억 픽셀이 나와 메모리가 못 버틴다
- 겹침 있는 타일로 나눠 처리 후 이어붙이는 `tile_process`(Real-ESRGAN
공식 구현과 동일 로직)가 필수.

**미검증**: 실제 사진에 대한 화질/아티팩트 평가는 아직 안 함 - 공식
가중치를 공식 아키텍처로 그대로 돌린다는 것만 확인(로드 시
`strict=True`가 통과하면 아키텍처가 체크포인트와 정확히 일치한다는
뜻)."""
import os
import urllib.request

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "models", "upscale")

# xinntao/Real-ESRGAN 공식 GitHub Release - 서드파티 변환본이 아닌 1차 소스.
_MODEL_URLS = {
    2: "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
    4: "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
}

UPSCALE_SCALES = sorted(_MODEL_URLS)
UPSCALE_ENGINES = ("pytorch", "onnx")


# ============================================================
# RRDBNet 아키텍처 - basicsr/archs/rrdbnet_arch.py에서 그대로 옮김
# (학습 전용 가중치 초기화 호출만 뺐다 - 어차피 바로 load_state_dict로
# 덮어써지므로 추론에는 불필요)
# ============================================================
class _ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat=64, num_grow_ch=32):
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class _RRDB(nn.Module):
    def __init__(self, num_feat, num_grow_ch=32):
        super().__init__()
        self.rdb1 = _ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = _ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = _ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


def _make_layer(block, num_blocks, **kwargs):
    return nn.Sequential(*[block(**kwargs) for _ in range(num_blocks)])


def _pixel_unshuffle(x, scale):
    b, c, hh, hw = x.size()
    out_channel = c * (scale ** 2)
    h, w = hh // scale, hw // scale
    x_view = x.view(b, c, h, scale, w, scale)
    return x_view.permute(0, 1, 3, 5, 2, 4).reshape(b, out_channel, h, w)


class _RRDBNet(nn.Module):
    """scale=2/4용 - Real-ESRGAN 공식 x2plus/x4plus 체크포인트와 같은
    구성(num_feat=64, num_block=23, num_grow_ch=32)."""

    def __init__(self, scale, num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32):
        super().__init__()
        self.scale = scale
        conv_in_ch = num_in_ch * 4 if scale == 2 else num_in_ch
        self.conv_first = nn.Conv2d(conv_in_ch, num_feat, 3, 1, 1)
        self.body = _make_layer(_RRDB, num_block, num_feat=num_feat, num_grow_ch=num_grow_ch)
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = _pixel_unshuffle(x, scale=2) if self.scale == 2 else x
        feat = self.conv_first(feat)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


# ============================================================
# 가중치 다운로드 + 모델 준비
# ============================================================
def _weights_path(scale):
    return os.path.join(_MODELS_DIR, f"RealESRGAN_x{scale}plus.pth")


def _onnx_path(scale):
    return os.path.join(_MODELS_DIR, f"RealESRGAN_x{scale}plus.onnx")


def download_weights(scale):
    """공식 가중치가 로컬에 없으면 받는다. 이미 있으면 바로 반환(재다운로드 안 함)."""
    if scale not in _MODEL_URLS:
        raise ValueError(f"지원하지 않는 scale: {scale} (지원: {UPSCALE_SCALES})")
    path = _weights_path(scale)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(_MODELS_DIR, exist_ok=True)
    req = urllib.request.Request(_MODEL_URLS[scale], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return path


def build_pytorch_model(scale):
    """가중치를 받아 RRDBNet(scale)에 로드하고 eval 모드로 반환.
    `strict=True`가 통과해야 체크포인트와 아키텍처가 정확히 일치한다는
    뜻 - 실패하면 벤더링한 구조가 잘못됐다는 신호."""
    weights_path = download_weights(scale)
    checkpoint = torch.load(weights_path, map_location="cpu")
    state_dict = checkpoint.get("params_ema", checkpoint.get("params", checkpoint))
    model = _RRDBNet(scale=scale)
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    return model


def ensure_onnx_model(scale):
    """ONNX 변환본이 캐시에 없으면 PyTorch 모델을 한 번 빌드해서
    `torch.onnx.export()`로 변환/저장 - 이후 추론은 이 파일 + onnxruntime
    만으로 가능(torch는 이 변환 1회에만 관여)."""
    path = _onnx_path(scale)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    model = build_pytorch_model(scale)
    dummy = torch.zeros(1, 3, 64, 64, dtype=torch.float32)
    os.makedirs(_MODELS_DIR, exist_ok=True)
    torch.onnx.export(
        model, dummy, path,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {2: "height", 3: "width"},
                      "output": {2: "height", 3: "width"}},
        opset_version=17,
        dynamo=False,  # dynamo=True(기본, torch>=2.x)는 onnxscript를 추가로
                       # 요구함 - 무거운 새 의존성 하나 더 늘리는 대신 레거시
                       # TorchScript 기반 익스포터로 충분해서 명시적으로 끔
    )
    return path


# ============================================================
# 타일 추론 - Real-ESRGAN 공식 tile_process()와 같은 로직
# (겹침 패딩만큼 잘라 처리한 뒤, 패딩을 뺀 중심부만 이어붙인다)
# ============================================================
def _tile_bounds(width, height, tile_size, tile_pad):
    tiles_x = -(-width // tile_size)   # ceil
    tiles_y = -(-height // tile_size)
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            in_x0, in_y0 = tx * tile_size, ty * tile_size
            in_x1, in_y1 = min(in_x0 + tile_size, width), min(in_y0 + tile_size, height)
            pad_x0, pad_y0 = max(in_x0 - tile_pad, 0), max(in_y0 - tile_pad, 0)
            pad_x1, pad_y1 = min(in_x1 + tile_pad, width), min(in_y1 + tile_pad, height)
            yield dict(in_x0=in_x0, in_y0=in_y0, in_x1=in_x1, in_y1=in_y1,
                       pad_x0=pad_x0, pad_y0=pad_y0, pad_x1=pad_x1, pad_y1=pad_y1)


def _tile_process(img_chw_f32, scale, tile_size, tile_pad, infer_fn):
    """img_chw_f32: (C, H, W) float32 [0, 1]. infer_fn(tile_chw_f32) ->
    (C, h*scale, w*scale) float32 - 엔진(torch/onnxruntime)별로 다른
    한 타일 추론만 주입받고, 타일 분할/이어붙이기는 공통이다."""
    c, height, width = img_chw_f32.shape
    output = np.zeros((c, height * scale, width * scale), dtype=np.float32)

    for b in _tile_bounds(width, height, tile_size, tile_pad):
        tile = img_chw_f32[:, b["pad_y0"]:b["pad_y1"], b["pad_x0"]:b["pad_x1"]]
        out_tile = infer_fn(tile)

        # 패딩 없는 원래 영역만 잘라서 최종 출력에 배치
        rel_x0 = (b["in_x0"] - b["pad_x0"]) * scale
        rel_y0 = (b["in_y0"] - b["pad_y0"]) * scale
        rel_w = (b["in_x1"] - b["in_x0"]) * scale
        rel_h = (b["in_y1"] - b["in_y0"]) * scale
        cropped = out_tile[:, rel_y0:rel_y0 + rel_h, rel_x0:rel_x0 + rel_w]

        out_x0, out_y0 = b["in_x0"] * scale, b["in_y0"] * scale
        output[:, out_y0:out_y0 + rel_h, out_x0:out_x0 + rel_w] = cropped

    return output


def upscale(img_bgr, scale=4, engine="onnx", tile_size=512, tile_pad=10):
    """img_bgr: uint8 (H, W, 3) BGR. 반환도 uint8 (H*scale, W*scale, 3) BGR.

    engine="pytorch"는 build_pytorch_model()로 매 호출 새로 로드한다(모델
    캐싱은 호출부 책임 - GUI/CLI에서 반복 호출 시 알아서 재사용할 것).
    engine="onnx"는 ensure_onnx_model()이 캐시된 .onnx를 재사용."""
    if scale not in _MODEL_URLS:
        raise ValueError(f"지원하지 않는 scale: {scale} (지원: {UPSCALE_SCALES})")
    if engine not in UPSCALE_ENGINES:
        raise ValueError(f"지원하지 않는 engine: {engine} (지원: {UPSCALE_ENGINES})")

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    chw = np.transpose(rgb, (2, 0, 1))  # (3, H, W)

    if engine == "pytorch":
        model = build_pytorch_model(scale)

        def infer_fn(tile_chw):
            with torch.no_grad():
                t = torch.from_numpy(tile_chw).unsqueeze(0)
                return model(t).squeeze(0).numpy()
    else:
        import onnxruntime
        onnx_path = ensure_onnx_model(scale)
        session = onnxruntime.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name

        def infer_fn(tile_chw):
            out = session.run(None, {input_name: tile_chw[np.newaxis, ...].astype(np.float32)})
            return out[0][0]

    out_chw = _tile_process(chw, scale, tile_size, tile_pad, infer_fn)
    out_rgb = np.clip(np.transpose(out_chw, (1, 2, 0)), 0.0, 1.0)
    out_bgr = cv2.cvtColor((out_rgb * 255.0).round().astype(np.uint8), cv2.COLOR_RGB2BGR)
    return out_bgr
