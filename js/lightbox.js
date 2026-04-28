(function () {
  const figures = [...document.querySelectorAll('figure')].filter(
    f => f.querySelector('a[download]') && f.querySelector('img')
  );
  if (!figures.length) return;

  // ── Lightbox (all devices) ────────────────────────────────────────────────────

  const images = figures.map(f => ({
    jpg:      f.querySelector('img').src,
    tif:      f.querySelector('a').href,
    caption:  f.querySelector('.caption-title')?.textContent?.trim() || '',
    filename: f.querySelector('.caption-filename')?.textContent?.trim() || '',
  }));

  const style = document.createElement('style');
  style.textContent = `
    #pli-lb {
      display: none; position: fixed; inset: 0; z-index: 9999;
      background: rgba(8,8,8,0.97);
      flex-direction: column; align-items: center; justify-content: center;
    }
    #pli-lb.open { display: flex; }
    #pli-lb-shell {
      width: 92vw; max-width: 1400px; min-width: 1000px;
      display: flex; flex-direction: column;
    }
    @media (max-width: 1080px) {
      #pli-lb-shell { min-width: 0; width: 96vw; }
    }
    #pli-lb-topbar {
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;
    }
    #pli-lb-counter {
      font-family: system-ui, sans-serif; font-size: 11px;
      letter-spacing: 0.1em; color: rgba(255,255,255,0.25);
    }
    #pli-lb-close {
      font-family: system-ui, sans-serif; font-size: 11px; letter-spacing: 0.08em;
      color: rgba(255,255,255,0.4); background: transparent;
      border: 0.5px solid rgba(255,255,255,0.2); padding: 5px 12px;
      cursor: pointer; transition: color 0.1s, border-color 0.1s; line-height: 1;
      outline: none;
    }
    #pli-lb-close:hover { color: rgba(255,255,255,0.9); border-color: rgba(255,255,255,0.55); }
    #pli-lb-close:focus-visible { outline: none; }
    #pli-lb-img-row {
      display: flex; align-items: center; gap: 12px;
    }
    #pli-lb-img-area {
      background: transparent; position: relative; flex: 1;
      display: flex; align-items: center; justify-content: center;
      height: 70vh; overflow: hidden;
    }
    #pli-lb-img {
      max-width: 100%; max-height: 70vh; object-fit: contain; display: block;
      cursor: zoom-in; user-select: none; -webkit-user-drag: none;
      -webkit-touch-callout: none; -webkit-user-select: none;
      transition: none;
    }
    #pli-lb-img.zoomed {
      max-width: none; max-height: none; width: auto; height: auto;
      cursor: grab; will-change: transform;
    }
    #pli-lb-img.panning { cursor: grabbing !important; }
    .pli-lb-nav {
      width: 36px; height: 36px; flex-shrink: 0; background: transparent;
      border: 0.5px solid transparent; color: rgba(255,255,255,0.5);
      font-size: 15px; display: flex; align-items: center; justify-content: center;
      cursor: pointer; user-select: none; transition: background 0.1s, color 0.1s; line-height: 1;
    }
    .pli-lb-nav:hover { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.9); }
    #pli-lb-meta {
      display: flex; justify-content: space-between; align-items: flex-start; gap: 1.5rem;
      border-top: 0.5px solid rgba(255,255,255,0.1); margin-top: 10px; padding-top: 10px;
    }
    #pli-lb-left { flex: 1; min-width: 0; }
    #pli-lb-caption {
      font-family: system-ui, sans-serif; font-size: 13px;
      color: rgba(255,255,255,0.72); margin-bottom: 4px; line-height: 1.4;
    }
    #pli-lb-filename {
      font-family: system-ui, sans-serif; font-size: 11px;
      font-family: monospace; color: rgba(255,255,255,0.3); word-break: break-all;
    }
    #pli-lb-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }
    #pli-lb-dl {
      font-family: system-ui, sans-serif; font-size: 11px; letter-spacing: 0.06em;
      color: rgba(255,255,255,0.38); background: transparent;
      border: 0.5px solid rgba(255,255,255,0.2); padding: 5px 12px;
      cursor: pointer; text-decoration: none; display: inline-block;
      transition: color 0.1s, border-color 0.1s; line-height: 1.4;
    }
    #pli-lb-dl:hover { color: rgba(255,255,255,0.88); border-color: rgba(255,255,255,0.55); }
    #pli-lb-cc { font-family: system-ui, sans-serif; font-size: 10px; color: rgba(255,255,255,0.18); }
  `;
  document.head.appendChild(style);

  const lb = document.createElement('div');
  lb.id = 'pli-lb';
  lb.setAttribute('role', 'dialog');
  lb.setAttribute('aria-modal', 'true');
  lb.setAttribute('aria-label', 'Image viewer');
  lb.innerHTML = `
    <div id="pli-lb-shell">
      <div id="pli-lb-topbar">
        <span id="pli-lb-counter"></span>
        <button id="pli-lb-close">&#x2715;</button>
      </div>
      <div id="pli-lb-img-row">
        <div class="pli-lb-nav" id="pli-lb-prev" role="button" aria-label="Previous image">&#8592;</div>
        <div id="pli-lb-img-area">
          <img id="pli-lb-img" alt="" />
        </div>
        <div class="pli-lb-nav" id="pli-lb-next" role="button" aria-label="Next image">&#8594;</div>
      </div>
      <div id="pli-lb-meta">
        <div id="pli-lb-left">
          <div id="pli-lb-caption"></div>
          <div id="pli-lb-filename"></div>
        </div>
        <div id="pli-lb-right">
          <a id="pli-lb-dl" href="#" download>download tiff</a>
          <div id="pli-lb-cc">CC0 1.0 Universal</div>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(lb);

  let current   = 0;
  let isZoomed  = false;
  let isPanning = false;
  let didPan    = false;
  let panX = 0, panY = 0;
  let startX = 0, startY = 0;
  let startPanX = 0, startPanY = 0;

  const elImg      = document.getElementById('pli-lb-img');
  const elCaption  = document.getElementById('pli-lb-caption');
  const elFilename = document.getElementById('pli-lb-filename');
  const elCounter  = document.getElementById('pli-lb-counter');
  const elDl       = document.getElementById('pli-lb-dl');
  const elImgArea  = document.getElementById('pli-lb-img-area');

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  function getPanLimits() {
    const maxX = Math.max(0, (elImg.naturalWidth  - elImgArea.clientWidth)  / 2);
    const maxY = Math.max(0, (elImg.naturalHeight - elImgArea.clientHeight) / 2);
    return { maxX, maxY };
  }

  function applyTransform() {
    elImg.style.transform = isZoomed ? `translate(${panX}px, ${panY}px)` : '';
  }

  function setZoom(on) {
    isZoomed = on;
    panX = 0; panY = 0;
    elImg.classList.toggle('zoomed', on);
    elImg.classList.remove('panning');
    applyTransform();
  }

  function show(index) {
    current = (index + images.length) % images.length;
    const img = images[current];
    setZoom(false);
    elImg.src              = img.jpg;
    elImg.alt              = img.caption;
    elCaption.textContent  = img.caption;
    elFilename.textContent = img.filename;
    elDl.href              = img.tif;
    elDl.download          = img.filename.replace(/\.jpg$/, '.tif');
    elCounter.textContent  = (current + 1) + ' / ' + images.length;
  }

  function open(index) {
    show(index);
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
    document.getElementById('pli-lb-close').focus();
  }

  function close() {
    lb.classList.remove('open');
    document.body.style.overflow = '';
    setZoom(false);
  }

  // ── Mouse: pan while zoomed, click to toggle zoom ────────────────────────────

  elImg.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    if (!isZoomed) return;
    isPanning = true;
    didPan    = false;
    startX    = e.clientX;
    startY    = e.clientY;
    startPanX = panX;
    startPanY = panY;
    elImg.classList.add('panning');
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!isPanning) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) didPan = true;
    const { maxX, maxY } = getPanLimits();
    panX = clamp(startPanX + dx, -maxX, maxX);
    panY = clamp(startPanY + dy, -maxY, maxY);
    applyTransform();
  });

  document.addEventListener('mouseup', e => {
    if (e.button !== 0) return;
    if (isPanning) {
      isPanning = false;
      elImg.classList.remove('panning');
      if (!didPan) setZoom(false);
      didPan = false;
      return;
    }
    if (e.target === elImg && !isZoomed) setZoom(true);
  });

  // ── Touch: tap to zoom, pan while zoomed, swipe to navigate ─────────────────

  let touchStartX = 0, touchStartY = 0;
  let touchPanStartX = 0, touchPanStartY = 0;
  let isTouchPanning = false;
  let touchMoved = false;

  elImg.addEventListener('touchstart', e => {
    e.preventDefault();
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchMoved = false;
    if (isZoomed) {
      isTouchPanning = true;
      touchPanStartX = panX;
      touchPanStartY = panY;
    }
  }, { passive: false });

  elImg.addEventListener('touchmove', e => {
    e.preventDefault();
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    const dx = t.clientX - touchStartX;
    const dy = t.clientY - touchStartY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) touchMoved = true;
    if (isZoomed && isTouchPanning) {
      const { maxX, maxY } = getPanLimits();
      panX = clamp(touchPanStartX + dx, -maxX, maxX);
      panY = clamp(touchPanStartY + dy, -maxY, maxY);
      applyTransform();
    }
  }, { passive: false });

  elImg.addEventListener('touchend', e => {
    e.preventDefault();
    const endX = e.changedTouches[0]?.clientX ?? touchStartX;
    const endY = e.changedTouches[0]?.clientY ?? touchStartY;
    if (isZoomed) {
      isTouchPanning = false;
      if (!touchMoved) setZoom(false);
    } else {
      if (!touchMoved) {
        setZoom(true);
      } else {
        const dx = endX - touchStartX;
        const dy = endY - touchStartY;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
          show(dx < 0 ? current + 1 : current - 1);
        }
      }
    }
  }, { passive: false });

  elImg.addEventListener('contextmenu', e => e.preventDefault());

  // ── Nav and keyboard ─────────────────────────────────────────────────────────

  figures.forEach((fig, i) => {
    fig.querySelector('a[download]').addEventListener('click', e => {
      e.preventDefault();
      open(i);
    });
  });

  document.getElementById('pli-lb-close').addEventListener('click', close);
  document.getElementById('pli-lb-prev').addEventListener('click', () => show(current - 1));
  document.getElementById('pli-lb-next').addEventListener('click', () => show(current + 1));
  lb.addEventListener('click', e => { if (e.target === lb) close(); });

  document.addEventListener('keydown', e => {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape')     { if (isZoomed) setZoom(false); else close(); }
    if (e.key === 'ArrowLeft')  show(current - 1);
    if (e.key === 'ArrowRight') show(current + 1);
  });

  // "View all N images" button — opens lightbox at first image
  document.querySelectorAll('.pli-view-all').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      open(parseInt(btn.dataset.index || '0', 10));
    });
  });

})();
