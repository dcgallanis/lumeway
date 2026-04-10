// Lumeway Feedback Widget — only injects on chat and dashboard pages
(function() {
  // Only show feedback on dashboard and chat pages
  var path = window.location.pathname;
  if (path.indexOf('/dashboard') === -1 && path.indexOf('/chat') === -1) return;
  // Don't inject if modal already exists (landing page, transition pages have inline version)
  if (document.getElementById('fbOverlay')) return;

  // Inject CSS
  var style = document.createElement('style');
  style.textContent = [
    '.fb-overlay{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,0.2);display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity 0.25s}',
    '.fb-overlay.open{opacity:1;pointer-events:auto}',
    '.fb-card{background:#FDFCFA;border-radius:16px;padding:32px;max-width:440px;width:90%;box-shadow:0 8px 32px rgba(44,74,94,0.12);position:relative}',
    '.fb-close{position:absolute;top:12px;right:16px;background:none;border:none;font-size:20px;color:#6B7B8D;cursor:pointer}',
    '.fb-close:hover{color:#2C4A5E}',
    ".fb-title{font-family:'Libre Baskerville',Georgia,serif;font-size:20px;color:#2C4A5E;margin-bottom:4px}",
    ".fb-sub{font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;color:#6B7B8D;font-weight:300;margin-bottom:20px}",
    ".fb-label{font-family:'Plus Jakarta Sans',sans-serif;font-size:12px;font-weight:500;color:#2C4A5E;margin-bottom:8px;display:block}",
    '.fb-areas{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}',
    ".fb-area{padding:8px 16px;border:1px solid #E8E0D6;border-radius:100px;background:#FAF7F2;color:#6B7B8D;font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;cursor:pointer;transition:all 0.15s}",
    '.fb-area:hover{border-color:#B8977E;color:#2C3E50}',
    '.fb-area.active{background:#2C4A5E;color:#FAF7F2;border-color:#2C4A5E}',
    '.fb-stars{display:flex;gap:6px;margin-bottom:16px}',
    '.fb-star{font-size:20px;color:#E8E0D6;cursor:pointer;transition:color 0.15s}',
    '.fb-star:hover,.fb-star.active{color:#B8977E}',
    ".fb-msg{width:100%;min-height:80px;padding:12px;border:1px solid #E8E0D6;border-radius:10px;font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:300;resize:vertical;margin-bottom:12px;background:#FAF7F2;color:#2C3E50}",
    '.fb-msg:focus{outline:none;border-color:#B8977E}',
    ".fb-email{width:100%;padding:10px 12px;border:1px solid #E8E0D6;border-radius:8px;font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:300;margin-bottom:16px;background:#FAF7F2;color:#2C3E50}",
    '.fb-email:focus{outline:none;border-color:#B8977E}',
    ".fb-send{width:100%;padding:12px;background:#C4704E;color:white;border:none;border-radius:10px;font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:500;cursor:pointer;transition:all 0.2s}",
    '.fb-send:hover{filter:brightness(1.08)}',
    ".fb-success{text-align:center;padding:40px 20px}",
    ".fb-success-icon{font-size:32px;margin-bottom:12px}",
    ".fb-success-msg{font-family:'Libre Baskerville',Georgia,serif;font-size:18px;color:#2C4A5E;margin-bottom:8px}",
    ".fb-success-sub{font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;color:#6B7B8D;font-weight:300}"
  ].join('\n');
  document.head.appendChild(style);

  // Inject HTML
  var div = document.createElement('div');
  div.innerHTML = '<div class="fb-overlay" id="fbOverlay" onclick="if(event.target===this)closeFeedback()">'
    + '<div class="fb-card">'
    + '<button class="fb-close" onclick="closeFeedback()">&times;</button>'
    + '<div id="fbForm">'
    + '<div class="fb-title">Share your feedback</div>'
    + '<div class="fb-sub">We read everything. This helps us make Lumeway better.</div>'
    + '<label class="fb-label">What is this about?</label>'
    + '<div class="fb-areas">'
    + '<button class="fb-area" onclick="selFbArea(this)" data-a="site">Site</button>'
    + '<button class="fb-area" onclick="selFbArea(this)" data-a="chat">Chat</button>'
    + '<button class="fb-area" onclick="selFbArea(this)" data-a="templates">Templates</button>'
    + '<button class="fb-area" onclick="selFbArea(this)" data-a="dashboard">Dashboard</button>'
    + '<button class="fb-area" onclick="selFbArea(this)" data-a="guides">Guides</button>'
    + '<button class="fb-area" onclick="selFbArea(this)" data-a="other">Other</button>'
    + '</div>'
    + '<label class="fb-label">How would you rate your experience?</label>'
    + '<div class="fb-stars">'
    + '<span class="fb-star" data-r="1" onclick="setFbR(1)">&#9733;</span>'
    + '<span class="fb-star" data-r="2" onclick="setFbR(2)">&#9733;</span>'
    + '<span class="fb-star" data-r="3" onclick="setFbR(3)">&#9733;</span>'
    + '<span class="fb-star" data-r="4" onclick="setFbR(4)">&#9733;</span>'
    + '<span class="fb-star" data-r="5" onclick="setFbR(5)">&#9733;</span>'
    + '</div>'
    + '<textarea class="fb-msg" id="fbMsg" placeholder="What\'s working? What\'s confusing? What do you wish existed?"></textarea>'
    + '<input class="fb-email" id="fbEmail" type="email" placeholder="Email (optional — only if you want a reply)">'
    + '<button class="fb-send" onclick="sendFb()">Send feedback</button>'
    + '</div>'
    + '<div id="fbSuccess" class="fb-success" style="display:none">'
    + '<div class="fb-success-icon">&#10003;</div>'
    + '<div class="fb-success-msg">Thank you</div>'
    + '<div class="fb-success-sub">Your feedback helps us build something better.</div>'
    + '</div>'
    + '</div></div>';
  document.body.appendChild(div.firstChild);

  // Global functions
  var fbArea = '', fbRating = 0;

  window.openFeedback = function() {
    document.getElementById('fbOverlay').classList.add('open');
    document.getElementById('fbForm').style.display = 'block';
    document.getElementById('fbSuccess').style.display = 'none';
    fbArea = ''; fbRating = 0;
    document.querySelectorAll('.fb-area').forEach(function(b) { b.classList.remove('active'); });
    document.querySelectorAll('.fb-star').forEach(function(s) { s.classList.remove('active'); });
    document.getElementById('fbMsg').value = '';
    document.getElementById('fbEmail').value = '';
  };

  window.closeFeedback = function() {
    document.getElementById('fbOverlay').classList.remove('open');
  };

  window.selFbArea = function(b) {
    document.querySelectorAll('.fb-area').forEach(function(x) { x.classList.remove('active'); });
    b.classList.add('active');
    fbArea = b.dataset.a;
  };

  window.setFbR = function(r) {
    fbRating = r;
    document.querySelectorAll('.fb-star').forEach(function(s) {
      s.classList.toggle('active', parseInt(s.dataset.r) <= r);
    });
  };

  window.sendFb = function() {
    var m = document.getElementById('fbMsg').value.trim();
    if (!fbArea) { alert('Please select what this is about.'); return; }
    if (!m) { alert('Please write your feedback.'); return; }
    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        area: fbArea,
        rating: fbRating || null,
        message: m,
        email: document.getElementById('fbEmail').value.trim(),
        page_url: window.location.href
      })
    }).then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        document.getElementById('fbForm').style.display = 'none';
        document.getElementById('fbSuccess').style.display = 'block';
        setTimeout(closeFeedback, 3000);
      }
    });
  };

  // Close on Escape
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && document.getElementById('fbOverlay').classList.contains('open')) {
      closeFeedback();
    }
  });
})();
