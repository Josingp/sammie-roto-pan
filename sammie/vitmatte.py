"""
ViTMatte 추론 전용 최소 구현 (PAN).

- 논문: Yao et al., "ViTMatte: Boosting Image Matting with Pretrained Plain Vision Transformers" (2023)
- 원본 코드: https://github.com/hustvl/ViTMatte (MIT)
- 이 파일은 Hugging Face transformers 의 VitDet/VitMatte 구현(Apache-2.0)에서
  추론에 필요한 부분만 옮긴 것으로, 가중치 이름이 같아서 hustvl/vitmatte-* 체크포인트를 그대로 읽는다.
- transformers 패키지를 설치하지 않아도 되도록 따로 둔다.

입력: (B, 4, H, W) — RGB 를 (x-0.5)/0.5 로 정규화한 3채널 + trimap(0 / 0.5 / 1) 1채널. H, W 는 32의 배수.
출력: (B, 1, H, W) 알파 (0~1)
"""

import math

import torch
import torch.nn.functional as F
from torch import nn

# 전역 어텐션 한 번에 올리는 (토큰 x 토큰) 원소 수 상한. 넘으면 헤드 단위로 나눠 계산해 메모리를 아낀다.
_MAX_ATTN_ELEMS = 48_000_000


class _Embeddings(nn.Module):
    def __init__(self, hidden, in_ch=4, patch=16, pretrain_tokens=14 * 14):
        super().__init__()
        self.position_embeddings = nn.Parameter(torch.zeros(1, pretrain_tokens + 1, hidden))
        self.projection = nn.Conv2d(in_ch, hidden, kernel_size=patch, stride=patch)

    def forward(self, x):
        x = self.projection(x)
        h, w = x.shape[-2:]
        pos = self.position_embeddings[:, 1:]
        size = int(math.sqrt(pos.shape[1]))
        pos = pos.reshape(1, size, size, -1).permute(0, 3, 1, 2)
        if size != h or size != w:
            pos = F.interpolate(pos.float(), size=(h, w), mode="bicubic", align_corners=False)
        return x + pos.to(x.dtype)


def _get_rel_pos(q_size, k_size, rel_pos):
    max_rel_dist = int(2 * max(q_size, k_size) - 1)
    if rel_pos.shape[0] != max_rel_dist:
        r = F.interpolate(
            rel_pos.float().reshape(1, rel_pos.shape[0], -1).permute(0, 2, 1),
            size=max_rel_dist,
            mode="linear",
        )
        r = r.reshape(-1, max_rel_dist).permute(1, 0).to(rel_pos.dtype)
    else:
        r = rel_pos
    q_coords = torch.arange(q_size, device=rel_pos.device)[:, None] * max(k_size / q_size, 1.0)
    k_coords = torch.arange(k_size, device=rel_pos.device)[None, :] * max(q_size / k_size, 1.0)
    relative_coords = (q_coords - k_coords) + (k_size - 1) * max(q_size / k_size, 1.0)
    return r[relative_coords.long()]


class _Attention(nn.Module):
    def __init__(self, dim, num_heads, input_size):
        super().__init__()
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = head_dim ** -0.5
        self.qkv = nn.Linear(dim, dim * 3, bias=True)
        self.proj = nn.Linear(dim, dim)
        self.rel_pos_h = nn.Parameter(torch.zeros(2 * input_size - 1, head_dim))
        self.rel_pos_w = nn.Parameter(torch.zeros(2 * input_size - 1, head_dim))

    def forward(self, x):                                   # (B, H, W, C)
        B, H, W, _ = x.shape
        tokens = H * W
        qkv = self.qkv(x).reshape(B, tokens, 3, self.num_heads, -1).permute(2, 0, 3, 1, 4)
        q, k, v = qkv.reshape(3, B * self.num_heads, tokens, -1).unbind(0)
        rel_h = _get_rel_pos(H, H, self.rel_pos_h).to(q.dtype)
        rel_w = _get_rel_pos(W, W, self.rel_pos_w).to(q.dtype)
        out = torch.empty_like(q)
        step = max(1, int(_MAX_ATTN_ELEMS // (tokens * tokens)))
        for s in range(0, q.shape[0], step):
            qs = q[s:s + step]
            attn = (qs * self.scale) @ k[s:s + step].transpose(-2, -1)
            rq = qs.reshape(-1, H, W, qs.shape[-1])
            bias_h = torch.einsum("bhwc,hkc->bhwk", rq, rel_h)
            bias_w = torch.einsum("bhwc,wkc->bhwk", rq, rel_w)
            attn = (attn.view(-1, H, W, H, W) + bias_h[:, :, :, :, None] + bias_w[:, :, :, None, :]).view(-1, tokens, tokens)
            out[s:s + step] = attn.softmax(dim=-1) @ v[s:s + step]
            del attn, bias_h, bias_w
        x = out.view(B, self.num_heads, H, W, -1).permute(0, 2, 3, 1, 4).reshape(B, H, W, -1)
        return self.proj(x)


class _LayerNorm2d(nn.Module):
    """채널 우선(N, C, H, W) 텐서용 LayerNorm"""

    def __init__(self, channels, eps=1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(channels))
        self.bias = nn.Parameter(torch.zeros(channels))
        self.eps = eps

    def forward(self, x):
        dtype = x.dtype
        x = x.float()                       # 반정밀도(fp16)에서 제곱이 넘치지 않도록 이 부분만 fp32 로 계산
        u = x.mean(1, keepdim=True)
        s = (x - u).pow(2).mean(1, keepdim=True)
        x = (x - u) / torch.sqrt(s + self.eps)
        x = self.weight[:, None, None].float() * x + self.bias[:, None, None].float()
        return x.to(dtype)


class _ResBottleneck(nn.Module):
    def __init__(self, channels, bottleneck):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, bottleneck, 1, bias=False)
        self.norm1 = _LayerNorm2d(bottleneck)
        self.act1 = nn.GELU()
        self.conv2 = nn.Conv2d(bottleneck, bottleneck, 3, padding=1, bias=False)
        self.norm2 = _LayerNorm2d(bottleneck)
        self.act2 = nn.GELU()
        self.conv3 = nn.Conv2d(bottleneck, channels, 1, bias=False)
        self.norm3 = _LayerNorm2d(channels)

    def forward(self, x):
        out = self.act1(self.norm1(self.conv1(x)))
        out = self.act2(self.norm2(self.conv2(out)))
        out = self.norm3(self.conv3(out))
        return x + out


class _Mlp(nn.Module):
    def __init__(self, dim, hidden):
        super().__init__()
        self.fc1 = nn.Linear(dim, hidden)
        self.act = nn.GELU()
        self.fc2 = nn.Linear(hidden, dim)

    def forward(self, x):
        return self.fc2(self.act(self.fc1(x)))


def _window_partition(x, ws):
    B, H, W, C = x.shape
    pad_h, pad_w = (-H) % ws, (-W) % ws
    x = F.pad(x, (0, 0, 0, pad_w, 0, pad_h))
    Hp, Wp = H + pad_h, W + pad_w
    x = x.view(B, Hp // ws, ws, Wp // ws, ws, C)
    return x.permute(0, 1, 3, 2, 4, 5).contiguous().view(-1, ws, ws, C), (Hp, Wp)


def _window_unpartition(windows, ws, padded, size):
    Hp, Wp = padded
    H, W = size
    B = windows.shape[0] // ((Hp // ws) * (Wp // ws))
    x = windows.view(B, Hp // ws, Wp // ws, ws, ws, -1)
    x = x.permute(0, 1, 3, 2, 4, 5).contiguous().view(B, Hp, Wp, -1)
    return x[:, :H, :W, :].contiguous()


class _Layer(nn.Module):
    def __init__(self, dim, num_heads, window_size, use_residual, global_size):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim, eps=1e-6)
        self.attention = _Attention(dim, num_heads, window_size if window_size > 0 else global_size)
        self.norm2 = nn.LayerNorm(dim, eps=1e-6)
        self.mlp = _Mlp(dim, dim * 4)
        self.window_size = window_size
        self.use_residual = use_residual
        if use_residual:
            self.residual = _ResBottleneck(dim, dim // 2)

    def forward(self, x):                                   # (B, C, H, W)
        x = x.permute(0, 2, 3, 1)
        shortcut = x
        x = self.norm1(x)
        if self.window_size > 0:
            H, W = x.shape[1], x.shape[2]
            x, padded = _window_partition(x, self.window_size)
        x = self.attention(x)
        if self.window_size > 0:
            x = _window_unpartition(x, self.window_size, padded, (H, W))
        x = shortcut + x
        x = x + self.mlp(self.norm2(x))
        x = x.permute(0, 3, 1, 2)
        if self.use_residual:
            x = self.residual(x)
        return x


class _Encoder(nn.Module):
    def __init__(self, dim, num_heads, depth, window_size, window_blocks, residual_blocks, global_size):
        super().__init__()
        self.layer = nn.ModuleList([
            _Layer(dim, num_heads, window_size if i in window_blocks else 0, i in residual_blocks, global_size)
            for i in range(depth)
        ])

    def forward(self, x):
        for layer in self.layer:
            x = layer(x)
        return x


class _Backbone(nn.Module):
    def __init__(self, dim, num_heads):
        super().__init__()
        self.embeddings = _Embeddings(dim)
        self.encoder = _Encoder(dim, num_heads, depth=12, window_size=14,
                                window_blocks=(0, 1, 3, 4, 6, 7, 9, 10), residual_blocks=(2, 5, 8, 11),
                                global_size=32)

    def forward(self, x):
        return self.encoder(self.embeddings(x))


class _BasicConv3x3(nn.Module):
    def __init__(self, in_ch, out_ch, stride=2):
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False)
        self.batch_norm = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU()

    def forward(self, x):
        return self.relu(self.batch_norm(self.conv(x)))


class _ConvStream(nn.Module):
    def __init__(self, in_ch=4, sizes=(48, 96, 192)):
        super().__init__()
        chans = [in_ch] + list(sizes)
        self.convs = nn.ModuleList([_BasicConv3x3(chans[i], chans[i + 1]) for i in range(len(sizes))])
        self.chans = chans

    def forward(self, x):
        feats = [x]
        for conv in self.convs:
            x = conv(x)
            feats.append(x)
        return feats


class _FusionBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = _BasicConv3x3(in_ch, out_ch, stride=1)

    def forward(self, features, detail):
        up = F.interpolate(features, scale_factor=2, mode="bilinear", align_corners=False)
        return self.conv(torch.cat([detail, up], dim=1))


class _Head(nn.Module):
    def __init__(self, in_ch, mid=16):
        super().__init__()
        self.matting_convs = nn.Sequential(
            nn.Conv2d(in_ch, mid, 3, 1, 1),
            nn.BatchNorm2d(mid),
            nn.ReLU(True),
            nn.Conv2d(mid, 1, 1, 1, 0),
        )

    def forward(self, x):
        return self.matting_convs(x)


class _Decoder(nn.Module):
    def __init__(self, dim, fusion=(256, 128, 64, 32)):
        super().__init__()
        self.convstream = _ConvStream()
        chans = self.convstream.chans
        fchans = [dim] + list(fusion)
        self.fusion_blocks = nn.ModuleList([
            _FusionBlock(fchans[i] + chans[-(i + 1)], fchans[i + 1]) for i in range(len(fusion))
        ])
        self.matting_head = _Head(fusion[-1])

    def forward(self, features, pixel_values):
        detail = self.convstream(pixel_values)
        n = len(self.fusion_blocks)
        for i in range(n):
            features = self.fusion_blocks[i](features, detail[n - i - 1])
        return torch.sigmoid(self.matting_head(features))


class ViTMatte(nn.Module):
    def __init__(self, dim=384, num_heads=6):
        super().__init__()
        self.backbone = _Backbone(dim, num_heads)
        self.decoder = _Decoder(dim)

    def forward(self, pixel_values):
        return self.decoder(self.backbone(pixel_values), pixel_values)


def load_vitmatte(path, device="cpu"):
    """체크포인트(.safetensors 또는 .bin/.pth)를 읽어 평가 모드 모델을 돌려준다. 크기(small/base)는 가중치에서 판별."""
    path = str(path)
    if path.endswith(".safetensors"):
        from safetensors.torch import load_file
        state = load_file(path, device="cpu")
    else:
        state = torch.load(path, map_location="cpu", weights_only=True)
    dim = state["backbone.embeddings.projection.weight"].shape[0]
    model = ViTMatte(dim=dim, num_heads=dim // 64)
    model.load_state_dict(state, strict=True)
    return model.to(device).eval()
