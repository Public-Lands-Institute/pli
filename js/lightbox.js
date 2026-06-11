(function () {
  const figures = [...document.querySelectorAll('figure')].filter(
    f => f.querySelector('a[download]') && f.querySelector('img')
  );
  if (!figures.length) return;

  // ── Viewer (same chrome as the map index lightbox) ───────────────────────────

  const images = figures.map(f => {
    const img = f.querySelector('img');
    return {
      jpg:      img.dataset.full || img.src,
      tif:      f.querySelector('a').href,
      raw:      f.dataset.raw || '',
      xmp:      f.dataset.xmp || '',
      caption:  f.querySelector('.caption-title')?.textContent?.trim() || '',
      filename: f.querySelector('.caption-filename')?.textContent?.trim() || '',
    };
  });

  const style = document.createElement('style');
  style.textContent = `
    #plb { position: fixed; inset: 0; z-index: 9999; background: rgba(12,12,12,0.97); display: none; flex-direction: column; }
    #plb.open { display: flex; }
    #plb-img-wrap { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 56px 72px 0; position: relative; }
    #plb-img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; opacity: 0; transition: opacity 0.2s; }
    #plb-img.loaded { opacity: 1; }
    #plb-spinner { position: absolute; color: rgba(255,255,255,0.3); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }
    #plb-bar { display: flex; align-items: center; justify-content: space-between; padding: 14px 72px 20px; gap: 24px; flex-shrink: 0; border-top: 1px solid rgba(255,255,255,0.07); }
    #plb-meta { flex: 1; min-width: 0; }
    #plb-caption { font-size: 12px; font-weight: 300; color: rgba(255,255,255,0.55); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
    #plb-filename { font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.3); }
    #plb-actions { display: flex; gap: 8px; flex-shrink: 0; }
    .plb-action { font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; text-decoration: none; padding: 5px 12px; border: 1px solid rgba(255,255,255,0.3); color: rgba(255,255,255,0.65); transition: border-color 0.15s, color 0.15s; white-space: nowrap; }
    .plb-action:hover { border-color: rgba(255,255,255,0.75); color: #e8e8e8; }
    .plb-action.hidden { display: none; }
    #plb-close { position: fixed; top: 18px; right: 24px; z-index: 10001; background: none; border: none; cursor: pointer; color: rgba(255,255,255,0.4); font-size: 22px; line-height: 1; transition: color 0.15s; }
    #plb-close:hover { color: #e8e8e8; }
    #plb-prev, #plb-next { position: fixed; top: 50%; transform: translateY(-50%); z-index: 10001; background: none; border: none; cursor: pointer; color: rgba(255,255,255,0.3); font-size: 36px; padding: 16px; transition: color 0.15s; line-height: 1; }
    #plb-prev { left: 8px; } #plb-next { right: 8px; }
    #plb-prev:hover, #plb-next:hover { color: #e8e8e8; }
    #plb-counter { position: fixed; top: 22px; left: 50%; transform: translateX(-50%); z-index: 10001; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255,255,255,0.25); }
    @media (max-width: 640px) {
      #plb-img-wrap { padding: 56px 16px 0; }
      #plb-bar { padding: 14px 16px 20px; flex-direction: column; align-items: flex-start; gap: 10px; }
      #plb-actions { flex-wrap: wrap; }
      #plb-prev, #plb-next { font-size: 28px; padding: 10px; }
      #plb-prev { left: 0; } #plb-next { right: 0; }
    }
  `;
  document.head.appendChild(style);

  const lb = document.createElement('div');
  lb.id = 'plb';
  lb.setAttribute('role', 'dialog');
  lb.setAttribute('aria-modal', 'true');
  lb.setAttribute('aria-label', 'Image viewer');
  lb.innerHTML = `
    <button id="plb-close" aria-label="Close">&#x2715;</button>
    <button id="plb-prev" aria-label="Previous image">&#x2039;</button>
    <button id="plb-next" aria-label="Next image">&#x203a;</button>
    <div id="plb-counter"></div>
    <div id="plb-img-wrap">
      <div id="plb-spinner">Loading</div>
      <img id="plb-img" src="" alt="">
    </div>
    <div id="plb-bar">
      <div id="plb-meta">
        <div id="plb-caption"></div>
        <div id="plb-filename"></div>
      </div>
      <div id="plb-actions">
        <a id="plb-tif" class="plb-action" href="#" download>Download TIFF</a>
        <a id="plb-raw" class="plb-action" href="#" download>RAW File</a>
        <a id="plb-xmp" class="plb-action" href="#" download>XML</a>
      </div>
    </div>
  `;
  document.body.appendChild(lb);

  const elImg      = document.getElementById('plb-img');
  const elSpinner  = document.getElementById('plb-spinner');
  const elCaption  = document.getElementById('plb-caption');
  const elFilename = document.getElementById('plb-filename');
  const elCounter  = document.getElementById('plb-counter');
  const elTif      = document.getElementById('plb-tif');
  const elRaw      = document.getElementById('plb-raw');
  const elXmp      = document.getElementById('plb-xmp');

  let current = 0;

  function show(index) {
    current = (index + images.length) % images.length;
    const img = images[current];
    elImg.classList.remove('loaded');
    elImg.src = '';
    elSpinner.style.display = 'block';
    elSpinner.textContent = 'Loading';
    elImg.src = img.jpg;
    elImg.alt = img.caption;
    elImg.onload  = () => { elSpinner.style.display = 'none'; elImg.classList.add('loaded'); };
    elImg.onerror = () => { elSpinner.textContent = 'Image unavailable'; };
    elCaption.textContent  = img.caption;
    elFilename.textContent = img.filename;
    elCounter.textContent  = (current + 1) + ' / ' + images.length;
    elTif.href = img.tif;
    elTif.setAttribute('download', img.filename.replace(/\.jpe?g$/i, '.tif'));
    elRaw.classList.toggle('hidden', !img.raw);
    if (img.raw) elRaw.href = img.raw;
    elXmp.classList.toggle('hidden', !img.xmp);
    if (img.xmp) elXmp.href = img.xmp;
  }

  function open(index) {
    show(index);
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
    document.getElementById('plb-close').focus();
  }

  function close() {
    lb.classList.remove('open');
    elImg.src = '';
    document.body.style.overflow = '';
  }

  figures.forEach((fig, i) => {
    fig.querySelector('a[download]').addEventListener('click', e => {
      e.preventDefault();
      open(i);
    });
  });

  document.querySelectorAll('.plb-view-all').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      open(0);
    });
  });

  document.getElementById('plb-close').addEventListener('click', close);
  document.getElementById('plb-prev').addEventListener('click', () => show(current - 1));
  document.getElementById('plb-next').addEventListener('click', () => show(current + 1));
  lb.addEventListener('click', e => { if (e.target === lb || e.target.id === 'plb-img-wrap') close(); });

  document.addEventListener('keydown', e => {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape')     close();
    if (e.key === 'ArrowLeft')  show(current - 1);
    if (e.key === 'ArrowRight') show(current + 1);
  });

  // Touch: swipe to navigate
  let sx = 0, sy = 0;
  elImg.addEventListener('touchstart', e => {
    if (e.touches.length !== 1) return;
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
  }, { passive: true });
  elImg.addEventListener('touchend', e => {
    const dx = (e.changedTouches[0]?.clientX ?? sx) - sx;
    const dy = (e.changedTouches[0]?.clientY ?? sy) - sy;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) show(dx < 0 ? current + 1 : current - 1);
  }, { passive: true });

})();
