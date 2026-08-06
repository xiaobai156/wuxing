from __future__ import annotations

IMAGE_OCR_JS = r"""
const period = arguments[0] || 0;
if (!period) return [];

function isInk(data, w, x, y) {
  const k = (y * w + x) * 4;
  const r = data[k], g = data[k + 1], b = data[k + 2];
  return (r < 130 && g < 130 && b < 130) || (r > 120 && g < 90 && b < 90);
}


function bitsFromImage(ctx, x1, y1, w, h, inkRatio = 0.15, pixelThreshold = 150) {
  const data = ctx.getImageData(x1, y1, w, h).data;
  const bits = [];
  for (let gy = 0; gy < 20; gy++) {
    for (let gx = 0; gx < 20; gx++) {
      let ink = 0, total = 0;
      const sx = Math.floor(gx * w / 20), ex = Math.floor((gx + 1) * w / 20);
      const sy = Math.floor(gy * h / 20), ey = Math.floor((gy + 1) * h / 20);
      for (let y = sy; y < ey; y++) {
        for (let x = sx; x < ex; x++) {
          const k = (y * w + x) * 4;
          if (data[k] < pixelThreshold && data[k + 1] < pixelThreshold && data[k + 2] < pixelThreshold) ink++;
          total++;
        }
      }
      bits.push(ink > total * inkRatio ? 1 : 0);
    }
  }
  return bits;
}

function bitsForChar(ch, font, pixelThreshold = 150) {
  const canvas = document.createElement("canvas");
  canvas.width = 90;
  canvas.height = 90;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "white";
  ctx.fillRect(0, 0, 90, 90);
  ctx.fillStyle = "black";
  ctx.font = font;
  ctx.textBaseline = "top";
  ctx.fillText(ch, 12, 6);
  const data = ctx.getImageData(0, 0, 90, 90).data;
  let x1 = 90, y1 = 90, x2 = 0, y2 = 0;
  for (let y = 0; y < 90; y++) {
    for (let x = 0; x < 90; x++) {
      const k = (y * 90 + x) * 4;
      if (data[k] < pixelThreshold && data[k + 1] < pixelThreshold && data[k + 2] < pixelThreshold) {
        x1 = Math.min(x1, x); x2 = Math.max(x2, x);
        y1 = Math.min(y1, y); y2 = Math.max(y2, y);
      }
    }
  }
  return bitsFromImage(ctx, x1, y1, x2 - x1 + 1, y2 - y1 + 1, 0.15, pixelThreshold);
}

function bitDistance(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++;
  return d;
}

function classifyTextChar(ctx, x1, y1, w, h, items, fonts, limit, inkRatio = 0.15, pixelThreshold = 150) {
  const actual = bitsFromImage(ctx, x1, y1, w, h, inkRatio, pixelThreshold);
  let best = null;
  let second = null;
  for (const font of fonts) {
    for (const item of items) {
      const score = bitDistance(actual, bitsForChar(item[1], font, pixelThreshold));
      if (!best || score < best.score) {
        second = best;
        best = { value: item[2], score };
      } else if (!second || score < second.score) {
        second = { value: item[2], score };
      }
    }
  }
  if (!best || best.score >= limit) return null;
  return {
    value: best.value,
    score: best.score,
    gap: second ? second.score - best.score : limit - best.score,
  };
}

function classifyWuxing(ctx, x1, y1, w, h) {
  const chars = [
    ["\u91d1", "\u91d1", "\u91d1\u884c"],
    ["\u6728", "\u6728", "\u6728\u884c"],
    ["\u6c34", "\u6c34", "\u6c34\u884c"],
    ["\u706b", "\u706b", "\u706b\u884c"],
    ["\u571f", "\u571f", "\u571f\u884c"],
  ];
  const fonts = [
    "42px Arial",
    "bold 42px Arial",
    "42px Microsoft YaHei",
    "bold 42px Microsoft YaHei",
    "42px SimHei",
    "bold 42px SimHei",
  ];
  return classifyTextChar(ctx, x1, y1, w, h, chars, fonts, 100);
}

function classifyWuxingIndependent(ctx, x1, y1, w, h) {
  const chars = [
    ["\u91d1", "\u91d1", "\u91d1\u884c"],
    ["\u6728", "\u6728", "\u6728\u884c"],
    ["\u6c34", "\u6c34", "\u6c34\u884c"],
    ["\u706b", "\u706b", "\u706b\u884c"],
    ["\u571f", "\u571f", "\u571f\u884c"],
  ];
  const fonts = [
    "40px Microsoft YaHei",
    "bold 40px Microsoft YaHei",
    "40px SimHei",
    "bold 40px SimHei",
  ];
  return classifyTextChar(ctx, x1, y1, w, h, chars, fonts, 90, 0.22, 170);
}

function classifyStatus(ctx, x1, y1, w, h) {
  const chars = [
    ["\u5bf9", "\u5bf9", "\u5bf9"],
    ["\u9519", "\u9519", "\u9519"],
    ["\u51c6", "\u51c6", "\u51c6"],
    ["\u4e2d", "\u4e2d", "\u4e2d"],
    ["\u8d62", "\u8d62", "\u8d62"],
  ];
  const fonts = [
    "34px Arial",
    "bold 34px Arial",
    "34px Microsoft YaHei",
    "bold 34px Microsoft YaHei",
    "34px SimHei",
    "bold 34px SimHei",
  ];
  return classifyTextChar(ctx, x1, y1, w, h, chars, fonts, 120);
}

function periodBandsForImage(img) {
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  const w = canvas.width, h = canvas.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  const ys = [];
  for (let y = 0; y < h; y++) {
    let count = 0;
    for (let x = 0; x < w; x += 3) if (isInk(data, w, x, y)) count++;
    if (count > 20) ys.push(y);
  }
  let bands = [];
  for (const y of ys) {
    if (!bands.length || y - bands[bands.length - 1].end > 3) bands.push({ start: y, end: y });
    else bands[bands.length - 1].end = y;
  }
  bands = bands
    .filter((b) => b.end - b.start >= 28 && b.end - b.start <= 40)
    .map((b) => ({ start: b.start, end: b.end, mid: Math.round((b.start + b.end) / 2) }));
  return { ctx, w, h, bands };
}

function componentsInRow(ctx, w, mid) {
  const data = ctx.getImageData(0, 0, w, ctx.canvas.height).data;
  const cols = [];
  const xStart = Math.floor(w * 0.55);
  const xEnd = Math.floor(w * 0.98);
  for (let x = xStart; x < xEnd; x++) {
    let count = 0;
    for (let y = Math.max(0, mid - 24); y <= Math.min(ctx.canvas.height - 1, mid + 24); y++) {
      if (isInk(data, w, x, y)) count++;
    }
    if (count > 1) cols.push(x);
  }
  const comps = [];
  for (const x of cols) {
    if (!comps.length || x - comps[comps.length - 1].x2 > 2) comps.push({ x1: x, x2: x });
    else comps[comps.length - 1].x2 = x;
  }
  return comps.map((c) => ({ ...c, w: c.x2 - c.x1 + 1 })).filter((c) => c.w > 4);
}

function componentBox(ctx, comp, mid) {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  let x1 = comp.x2, x2 = comp.x1, y1 = Math.min(h - 1, mid + 24), y2 = Math.max(0, mid - 24);
  for (let y = Math.max(0, mid - 24); y <= Math.min(h - 1, mid + 24); y++) {
    for (let x = comp.x1; x <= comp.x2; x++) {
      const k = (y * w + x) * 4;
      if (data[k] < 150 && data[k + 1] < 150 && data[k + 2] < 150) {
        x1 = Math.min(x1, x); x2 = Math.max(x2, x);
        y1 = Math.min(y1, y); y2 = Math.max(y2, y);
      }
    }
  }
  return { x1, y1, w: x2 - x1 + 1, h: y2 - y1 + 1 };
}

function componentsInRange(ctx, w, mid, startRatio, endRatio) {
  const data = ctx.getImageData(0, 0, w, ctx.canvas.height).data;
  const cols = [];
  const xStart = Math.floor(w * startRatio);
  const xEnd = Math.floor(w * endRatio);
  for (let x = xStart; x < xEnd; x++) {
    let count = 0;
    for (let y = Math.max(0, mid - 24); y <= Math.min(ctx.canvas.height - 1, mid + 24); y++) {
      if (isInk(data, w, x, y)) count++;
    }
    if (count > 1) cols.push(x);
  }
  const comps = [];
  for (const x of cols) {
    if (!comps.length || x - comps[comps.length - 1].x2 > 2) comps.push({ x1: x, x2: x });
    else comps[comps.length - 1].x2 = x;
  }
  return comps.map((c) => ({ ...c, w: c.x2 - c.x1 + 1 })).filter((c) => c.w > 4);
}

function classifyPeriod(ctx, w, mid) {
  const digits = Array.from({ length: 10 }, (_, value) => [String(value), String(value), String(value)]);
  const fonts = [
    "40px Arial",
    "bold 40px Arial",
    "40px Microsoft YaHei",
    "bold 40px Microsoft YaHei",
    "40px SimHei",
    "bold 40px SimHei",
  ];
  const recognized = [];
  for (const component of componentsInRange(ctx, w, mid, 0.01, 0.38)) {
    if (component.w < 8 || component.w > 40) continue;
    const box = componentBox(ctx, component, mid);
    const result = classifyTextChar(ctx, box.x1, box.y1, box.w, box.h, digits, fonts, 70, 0.15, 150);
    if (!result || result.gap < 6) continue;
    recognized.push({ component, result });
  }
  if (!recognized.length) return null;
  const runs = [];
  for (const item of recognized) {
    const previous = runs[runs.length - 1];
    if (!previous || item.component.x1 - previous[previous.length - 1].component.x2 > 14) {
      runs.push([item]);
    } else {
      previous.push(item);
    }
  }
  const candidates = runs
    .filter((run) => run.length >= 2 && run.length <= 4)
    .map((run) => ({
      period: Number(run.map((item) => item.result.value).join("")),
      score: Math.max(...run.map((item) => item.result.score)),
      gap: Math.min(...run.map((item) => item.result.gap)),
    }))
    .filter((candidate) => candidate.period > 0 && candidate.period < 10000);
  if (candidates.length !== 1) return null;
  const candidate = candidates[0];
  return {
    ...candidate,
    evidence: `${candidate.period}\u671f`,
    source: "pixel_ocr",
  };
}

const images = Array.from(document.images)
  .filter((img) => img.naturalWidth > 700 && img.naturalHeight > 900)
  .sort((a, b) => (a.getBoundingClientRect().top + window.scrollY) - (b.getBoundingClientRect().top + window.scrollY));

for (const img of images) {
  const item = periodBandsForImage(img);
  if (item.bands.length < 15) continue;
  const lines = [];
  for (const band of item.bands) {
    const periodResult = classifyPeriod(item.ctx, item.w, band.mid);
    if (!periodResult || ![period - 1, period].includes(periodResult.period)) continue;
    const comps = componentsInRow(item.ctx, item.w, band.mid);
    const charComp = comps.find((c) => c.x1 > item.w * 0.68 && c.w >= 20 && c.w <= 45);
    if (!charComp) continue;
    const box = componentBox(item.ctx, charComp, band.mid);
    const wuxing = classifyWuxing(item.ctx, box.x1, box.y1, box.w, box.h);
    const independentWuxing = classifyWuxingIndependent(item.ctx, box.x1, box.y1, box.w, box.h);
    if (!wuxing || !independentWuxing || wuxing.value !== independentWuxing.value) continue;
    const statusComp = comps.slice().reverse().find((c) => c.x1 > item.w * 0.78 && c.w >= 18 && c.w <= 45);
    let status = "";
    let statusScore = null;
    if (statusComp) {
      const statusBox = componentBox(item.ctx, statusComp, band.mid);
      const statusResult = classifyStatus(item.ctx, statusBox.x1, statusBox.y1, statusBox.w, statusBox.h);
      if (statusResult) {
        status = statusResult.value;
        statusScore = statusResult.score;
      }
    }
    const openComp = comps.find((c) => c.x1 > item.w * 0.76 && c.x1 < item.w * 0.88 && c.w >= 20 && c.w <= 45);
    let openWuxing = "";
    let openWuxingScore = null;
    if (openComp) {
      const openBox = componentBox(item.ctx, openComp, band.mid);
      const openResult = classifyWuxing(item.ctx, openBox.x1, openBox.y1, openBox.w, openBox.h);
      if (openResult) {
        openWuxing = openResult.value;
        openWuxingScore = openResult.score;
      }
    }
    const openText = `寮€:${openWuxing || "鍥剧墖璇嗗埆"}`;
    const raw = `${periodResult.period}鏈?銆愬浘鐗囪瘑鍒€戙€?{wuxing.value}銆?${openText} ${status || ""}`;
    const validatedRaw = `${periodResult.period}\u671f\u3010\u56fe\u7247\u8bc6\u522b\u3011\u3010${wuxing.value}\u3011`;
    lines.push({
      period: periodResult.period,
      wuxing: wuxing.value,
      wuxingScore: wuxing.score,
      wuxingGap: wuxing.gap,
      independentPeriod: periodResult.period,
      periodEvidence: periodResult.evidence,
      periodEvidenceSource: periodResult.source,
      periodScore: periodResult.score,
      periodGap: periodResult.gap,
      independentWuxing: independentWuxing.value,
      independentWuxingScore: independentWuxing.score,
      openWuxing,
      openWuxingScore,
      status,
      statusScore,
      raw: validatedRaw,
    });
  }
  if (lines.some((line) => line.period === period)) return lines;
}
return [];
"""
