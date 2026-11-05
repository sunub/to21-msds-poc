"use client";

/*
 * 올린 원본 PDF를 pdf.js로 한 쪽씩 그린다. 그림(canvas) 위에 투명한 글자 층을 얹어 근거를 강조한다.
 * 글자 층은 고를 수 없다(pdf.css). 끌면 글자 위에서도 원문을 옮긴다.
 * 크게·작게(버튼, Ctrl/⌘+휠, +/- 키), 폭·쪽 맞춤, 두 번 눌러 확대, 끌어서 이동, PageUp/PageDown.
 * pdf.js 보조 파일은 public/pdfjs 에 있다 (scripts/copy-pdfjs.mjs). 외부에서 받는 것은 없다.
 */
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { pageBoxesQuery, pdfUrl } from "@/api/documents";
import { Button, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";
import { CSS_UNITS, clampScale, matchSpans, resolveScale, stepScale, scrollWithin, zoomPercent, type Highlight, type Zoom } from "@/lib/viewer";

const ASSETS = "/pdfjs";
const PAD = 16;

// 문서마다 한 번만 받는다. 탭을 옮겨도 다시 받지 않는다
const documents = new Map<string, Promise<PDFDocumentProxy>>();
function loadPdf(docId: string): Promise<PDFDocumentProxy> {
  let task = documents.get(docId);
  if (!task) {
    task = import("pdfjs-dist").then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = `${ASSETS}/pdf.worker.min.mjs`;
      return pdfjs.getDocument({
        url: pdfUrl(docId),
        cMapUrl: `${ASSETS}/cmaps/`,
        cMapPacked: true,
        standardFontDataUrl: `${ASSETS}/standard_fonts/`,
        wasmUrl: `${ASSETS}/wasm/`,
        iccUrl: `${ASSETS}/iccs/`,
      }).promise;
    });
    task.catch(() => documents.delete(docId));
    documents.set(docId, task);
  }
  return task;
}

// 배율은 쪽을 넘기거나 다른 탭으로 가도 그대로 둔다
let lastZoom: Zoom = "width";

type Anchor = { x: number; y: number; cx: number; cy: number; from: number };

export function PdfViewer({
  docId,
  page,
  onPage,
  onPages,
  highlight,
  className,
}: {
  docId: string;
  page: number;
  onPage: (page: number) => void;
  /** PDF를 연 뒤 전체 쪽 수 */
  onPages?: (total: number) => void;
  highlight?: Highlight;
  className?: string;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [failed, setFailed] = useState(false);
  const [current, setCurrent] = useState<{ no: number; proxy: PDFPageProxy } | null>(null);
  const [zoom, setZoomState] = useState<Zoom>(lastZoom);
  const [box, setBox] = useState({ width: 0, height: 0 });
  const [drawn, setDrawn] = useState(0);
  // 근거를 받았는데 원본 PDF 글자 층에서 못 찾음 (글꼴이 깨진 PDF·스캔본 등)
  const [missed, setMissed] = useState(false);
  // 원본 PDF 글자 층에서 못 찾으면 OCR이 읽은 글의 자리로 강조한다 (글꼴이 깨진 PDF·스캔본). 쪽 이미지 픽셀 기준 [x0, y0, x1, y1]
  const [ocrMarks, setOcrMarks] = useState<{ boxes: number[][]; width: number; height: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayer = useRef<HTMLDivElement>(null);
  const anchor = useRef<Anchor | null>(null);
  const scrolledTo = useRef("");
  const onPagesRef = useRef(onPages);
  onPagesRef.current = onPages;

  useEffect(() => {
    let live = true;
    setFailed(false);
    loadPdf(docId).then(
      (doc) => {
        if (!live) return;
        setPdf(doc);
        onPagesRef.current?.(doc.numPages);
      },
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [docId]);

  const total = pdf?.numPages ?? 0;
  const pageNo = total ? Math.min(Math.max(1, page), total) : page;

  useEffect(() => {
    if (!pdf) return;
    let live = true;
    pdf.getPage(pageNo).then(
      (proxy) => live && setCurrent({ no: pageNo, proxy }),
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [pdf, pageNo]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setBox((b) => (b.width === width && b.height === height ? b : { width, height }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [pdf]);

  const base = current?.proxy.getViewport({ scale: 1 });
  const scale = base && box.width > 0 ? resolveScale(zoom, base, box, PAD) : 0;
  const scaleRef = useRef(scale);
  scaleRef.current = scale;

  const setZoom = useCallback((next: Zoom, at?: { cx: number; cy: number }) => {
    const el = scroller.current;
    const from = scaleRef.current;
    if (el && from > 0) {
      const cx = at?.cx ?? el.clientWidth / 2;
      const cy = at?.cy ?? el.clientHeight / 2;
      anchor.current = { x: el.scrollLeft + cx - PAD, y: el.scrollTop + cy - PAD, cx, cy, from };
    }
    lastZoom = next;
    setZoomState(next);
  }, []);

  // 배율을 바꾼 뒤에도 누른 자리(또는 가운데)가 같은 곳에 오게 스크롤을 옮긴다
  useLayoutEffect(() => {
    const el = scroller.current;
    const a = anchor.current;
    if (!el || !a || !scale) return;
    anchor.current = null;
    const r = scale / a.from;
    el.scrollLeft = a.x * r + PAD - a.cx;
    el.scrollTop = a.y * r + PAD - a.cy;
  }, [scale]);

  // 그림과 글자 층. 화면 밀도(dpr)만큼 크게 그려 확대해도 흐리지 않다
  useEffect(() => {
    if (!current || !scale || !canvas.current || !textLayer.current) return;
    const viewport = current.proxy.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;
    const cv = canvas.current;
    cv.width = Math.floor(viewport.width * dpr);
    cv.height = Math.floor(viewport.height * dpr);
    const render = current.proxy.render({
      canvas: cv,
      viewport,
      transform: dpr === 1 ? undefined : [dpr, 0, 0, dpr, 0, 0],
    });
    const layer = textLayer.current;
    layer.replaceChildren();
    let text: { cancel: () => void } | null = null;
    let live = true;
    void import("pdfjs-dist").then(async ({ TextLayer }) => {
      if (!live) return;
      const t = new TextLayer({ textContentSource: current.proxy.streamTextContent(), container: layer, viewport });
      text = t;
      try {
        await t.render();
        if (live) setDrawn((n) => n + 1);
      } catch {
        // 취소
      }
    });
    render.promise.catch(() => {});
    return () => {
      live = false;
      render.cancel();
      text?.cancel();
    };
  }, [current, scale]);

  const ocr = useQuery({ ...pageBoxesQuery(docId, pageNo), enabled: !!highlight });

  // 근거 강조. 쪽이나 근거가 바뀔 때만 그 자리로 스크롤한다 (배율만 바꾸면 보던 자리를 지킨다)
  useEffect(() => {
    const layer = textLayer.current;
    if (!layer || !drawn) return;
    const spans = [...layer.querySelectorAll<HTMLElement>(":scope span:not(.markedContent)")];
    spans.forEach((s) => s.classList.remove("hit"));
    const hits = matchSpans(
      spans.map((s) => s.textContent ?? ""),
      highlight,
    ).map((i) => spans[i]);
    hits.forEach((s) => s.classList.add("hit"));
    const asked = typeof highlight === "string" ? highlight.trim() !== "" : (highlight?.length ?? 0) > 0;
    const boxes = ocr.data;
    const ocrHits =
      hits.length === 0 && boxes?.width && boxes.height
        ? matchSpans(boxes.items.map((i) => i.text), highlight).map((i) => boxes.items[i].box)
        : [];
    setOcrMarks(ocrHits.length && boxes?.width && boxes.height ? { boxes: ocrHits, width: boxes.width, height: boxes.height } : null);
    // OCR 기록을 받는 중이면 아직 못 찾았다고 하지 않는다
    setMissed(asked && hits.length === 0 && ocrHits.length === 0 && !ocr.isFetching);
    const key = `${current?.no}|${JSON.stringify(highlight ?? null)}`;
    if (hits[0] && scroller.current && scrolledTo.current !== key) {
      scrollWithin(scroller.current, hits[0], "center");
      scrolledTo.current = key;
    } else if (!ocrHits.length) scrolledTo.current = key;
  }, [drawn, highlight, current, ocr.data, ocr.isFetching]);

  // OCR 자리 강조는 그린 뒤에 그 자리로 옮긴다
  useEffect(() => {
    const first = scroller.current?.querySelector<HTMLElement>(".ocr-hit");
    const key = `${current?.no}|${JSON.stringify(highlight ?? null)}`;
    if (!first || !scroller.current || scrolledTo.current === key) return;
    scrollWithin(scroller.current, first, "center");
    scrolledTo.current = key;
  }, [ocrMarks, current, highlight]);

  // Ctrl/⌘ + 휠: 커서 자리를 중심으로 크게·작게 (브라우저 확대 대신)
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey) || !scaleRef.current) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      setZoom(clampScale(scaleRef.current * Math.exp(-e.deltaY * 0.002)), { cx: e.clientX - rect.left, cy: e.clientY - rect.top });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [pdf, setZoom]);

  // 끌어서 이동. 글자 위에서 시작해도 옮긴다 (글 고르기는 막아 두었다)
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = scroller.current;
    if (!el || e.button !== 0) return;
    if (el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight) return;
    drag.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop };
    el.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = scroller.current;
    const d = drag.current;
    if (!el || !d) return;
    el.scrollLeft = d.left - (e.clientX - d.x);
    el.scrollTop = d.top - (e.clientY - d.y);
  };
  const endDrag = () => {
    drag.current = null;
  };

  // 맞춤으로 보고 있으면 두 번 눌러 그 자리를 2배로, 배율을 정해 보고 있으면 폭 맞춤으로 돌아간다
  const onDoubleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = scroller.current;
    if (!el || !scale) return;
    window.getSelection()?.removeAllRanges();
    const rect = el.getBoundingClientRect();
    const at = { cx: e.clientX - rect.left, cy: e.clientY - rect.top };
    setZoom(typeof zoom === "number" ? "width" : clampScale(scale * 2), at);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "PageDown" && pageNo < total) onPage(pageNo + 1);
    else if (e.key === "PageUp" && pageNo > 1) onPage(pageNo - 1);
    else if ((e.key === "+" || e.key === "=") && scale) setZoom(stepScale(scale, 1));
    else if (e.key === "-" && scale) setZoom(stepScale(scale, -1));
    else if (e.key === "0") setZoom("width");
    else return;
    e.preventDefault();
  };

  if (failed) {
    return (
      <div className={cn("flex flex-1 flex-col items-center justify-center gap-2 rounded-md bg-paper p-6 text-center", className)}>
        <p>원본 PDF를 열지 못했습니다.</p>
        <p className="text-sm text-mut">&quot;추출 텍스트&quot;로 바꾸면 PDF에서 읽어 낸 텍스트를 볼 수 있습니다.</p>
      </div>
    );
  }

  const width = base && scale ? base.width * scale : 0;
  const height = base && scale ? base.height * scale : 0;
  const pannable = width + PAD * 2 > box.width + 1 || height + PAD * 2 > box.height + 1;

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-2", className)}>
      <div role="toolbar" aria-label="원문 크기" className="flex flex-wrap items-center gap-1.5">
        <Button aria-label="작게" disabled={!scale} onClick={() => setZoom(stepScale(scale, -1))} className="w-9 px-0 text-lg">
          −
        </Button>
        <Button
          aria-label="실제 크기로"
          title="누르면 100%"
          disabled={!scale}
          onClick={() => setZoom(CSS_UNITS)}
          className="w-16 px-0 tabular-nums"
        >
          {scale ? `${zoomPercent(scale)}%` : "-"}
        </Button>
        <Button aria-label="크게" disabled={!scale} onClick={() => setZoom(stepScale(scale, 1))} className="w-9 px-0 text-lg">
          +
        </Button>
        <Button variant={zoom === "width" ? "outline" : "default"} aria-pressed={zoom === "width"} onClick={() => setZoom("width")}>
          폭 맞춤
        </Button>
        <Button variant={zoom === "page" ? "outline" : "default"} aria-pressed={zoom === "page"} onClick={() => setZoom("page")}>
          페이지 맞춤
        </Button>
        <a
          href={`${pdfUrl(docId)}#page=${pageNo}`}
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-sm font-medium"
        >
          새 창에서 열기 ↗
        </a>
      </div>
      {missed && (
        <p role="status" className="m-0 text-sm text-amb-text">
          원본 PDF에서 이 값의 위치를 찾지 못했습니다. 위의 &quot;추출 텍스트&quot;에서 확인해 주세요.
        </p>
      )}
      <div
        ref={scroller}
        tabIndex={0}
        aria-label={`원본 ${pageNo}페이지. 두 번 누르면 확대, Ctrl+휠로 크기 조절, PageUp·PageDown으로 페이지 이동`}
        onKeyDown={onKeyDown}
        onDoubleClick={onDoubleClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          "relative min-h-0 flex-1 overflow-auto rounded-md bg-paper",
          pannable && "cursor-grab active:cursor-grabbing",
        )}
        style={{ padding: PAD }}
      >
        {!current || !scale ? (
          <div aria-hidden="true" className="mx-auto grid max-w-full gap-2.5 bg-white p-6">
            <Skeleton className="w-full" />
            <Skeleton className="w-4/5" />
            <Skeleton className="w-2/3" />
          </div>
        ) : null}
        <div
          className={cn("relative mx-auto bg-white shadow-[0_1px_4px_rgb(0_0_0/0.18)]", (!current || !scale) && "hidden")}
          style={{ width, height, ["--total-scale-factor" as string]: scale }}
        >
          <canvas ref={canvas} aria-label={`원문 ${pageNo}페이지`} role="img" style={{ width, height }} className="block" />
          <div ref={textLayer} className="textLayer" />
          {ocrMarks?.boxes.map(([x0, y0, x1, y1], i) => (
            <div
              key={i}
              aria-hidden="true"
              className="ocr-hit pointer-events-none absolute"
              style={{
                left: (x0 / ocrMarks.width) * width,
                top: (y0 / ocrMarks.height) * height,
                width: ((x1 - x0) / ocrMarks.width) * width,
                height: ((y1 - y0) / ocrMarks.height) * height,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
