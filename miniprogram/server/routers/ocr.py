"""图片 OCR：计划图 → 文本行（供前端批量导入解析）。

ponytail: RapidOCR 引擎全局懒加载单例，首次请求约 2-3 秒，之后毫秒级；
识别质量依赖拍照清晰度，失败时返回空文本由前端提示。
"""
from fastapi import APIRouter, UploadFile, File, Depends

from deps import get_current_user

router = APIRouter(prefix='/api/v1/ocr', tags=['ocr'])

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


@router.post('/image')
async def ocr_image(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    import io

    import numpy as np
    from PIL import Image

    data = await file.read()
    img = Image.open(io.BytesIO(data)).convert('RGB')
    result, _ = _get_engine()(np.array(img))
    # result: [[box, text, score], ...] 自上而下即阅读顺序（score 可能是 str）
    lines = []
    for r in (result or []):
        try:
            if r[1] and float(r[2]) > 0.5:
                lines.append(r[1])
        except (ValueError, IndexError):
            continue
    return {'text': '\n'.join(lines), 'count': len(lines)}
