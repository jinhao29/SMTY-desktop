/**
 * 头像选取与压缩（跨端）
 * 微信端：chooseImage(compressed) → 大图 compressImage → fs 读 base64
 * H5 端：canvas 裁剪为 240x240 jpeg
 */
export function pickAvatar() {
  return new Promise((resolve, reject) => {
    uni.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      success: ({ tempFilePaths }) => {
        _convert(tempFilePaths[0]).then(resolve).catch(reject)
      },
      fail: () => reject(new Error('cancel')),
    })
  })
}

async function _convert(path) {
  // #ifdef MP-WEIXIN
  const fs = uni.getFileSystemManager()
  let fpath = path
  try {
    const stat = fs.statSync(path)
    if (stat.size > 600 * 1024) {
      const res = await uni.compressImage({ src: path, quality: 50 })
      fpath = res.tempFilePath
    }
  } catch (e) { /* stat 不可用时直接读原图 */ }
  const b64 = fs.readFileSync(fpath, 'base64')
  return 'data:image/jpeg;base64,' + b64
  // #endif
  // #ifdef H5
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const S = 240
      const c = document.createElement('canvas')
      c.width = S
      c.height = S
      const ctx = c.getContext('2d')
      const r = Math.max(S / img.width, S / img.height)
      const w = img.width * r
      const h = img.height * r
      ctx.drawImage(img, (S - w) / 2, (S - h) / 2, w, h)
      resolve(c.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = reject
    img.src = path
  })
  // #endif
}
