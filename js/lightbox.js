(function () {
  const figures = [...document.querySelectorAll('figure')].filter(
    f => f.querySelector('a[download]') && f.querySelector('img')
  );
  if (!figures.length) return;

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
    #pli-lb-shell { width: 92vw; max-width: 960px; display: flex; flex-direction: column; }
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
    }
    #pli-lb-close:hover { color: rgba(255,255,255,0.9); border-color: rgba(255,255,255,0.55); }
    #pli-lb-img-area {
      background: #0d0d0d; position: relative;
      display: flex; align-items: center; justify-content: center;
      max-height: 70vh; overflow: hidden;
    }
    #pli-lb-img { max-width: 100%; max-height: 70vh; object-fit: contain; display: block; }
    .pli-lb-nav {
      position: absolute; top: 50%; transform: translateY(-50%);
      width: 36px; height: 36px; background: rgba(0,0,0,0.45);
      border: 0.5px solid rgba(255,255,255,0.15); color: rgba(255,255,255,0.5);
      font-size: 15px; display: flex; align-items: center; justify-content: center;
      cursor: pointer; user-select: none; transition: background 0.1s, color 0.1s; line-height: 1;
    }
    .pli-lb-nav:hover { background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.9); }
    #pli-lb-prev { left: 8px; }
    #pli-lb-next { right: 8px; }
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
    @media (max-width: 480px) {
      .pli-img-hidden { display: none !important; }
      .pli-show-more {
        display: block; width: 100%; padding: 10px 0;
        font-family: system-ui, sans-serif; font-size: 10px;
        text-transform: uppercase; letter-spacing: 0.16em;
        color: var(--muted); background: transparent;
        border: 1px solid var(--border); cursor: pointer;
        margin-top: 4px;
      }
      .pli-show-more:hover { color: var(--fg); }
    }
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
      <div id="pli-lb-img-area">
        <div class="pli-lb-nav" id="pli-lb-prev" role="button" aria-label="Previous image">&#8592;</div>
        <img id="pli-lb-img" alt="" />
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

  let current = 0;
  const elImg      = document.getElementById('pli-lb-img');
  const elCaption  = document.getElementById('pli-lb-caption');
  const elFilename = document.getElementById('pli-lb-filename');
  const elCounter  = document.getElementById('pli-lb-counter');
  const elDl       = document.getElementById('pli-lb-dl');

  function show(index) {
    current = (index + images.length) % images.length;
    const img = images[current];
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
  }

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
    if (e.key === 'Escape')     close();
    if (e.key === 'ArrowLeft')  show(current - 1);
    if (e.key === 'ArrowRight') show(current + 1);
  });

  // Mobile image cap: always inject markup; CSS hides extras at <=480px
  const CAP = 4;
  if (figures.length > CAP) {
    figures.slice(CAP).forEach(f => f.classList.add('pli-img-hidden'));
    const btn = document.createElement('button');
    btn.className = 'pli-show-more';
    btn.textContent = 'Show ' + (figures.length - CAP) + ' more';
    figures[CAP - 1].insertAdjacentElement('afterend', btn);
    btn.addEventListener('click', () => {
      figures.slice(CAP).forEach(f => f.classList.remove('pli-img-hidden'));
      btn.remove();
    });
  }
})();
