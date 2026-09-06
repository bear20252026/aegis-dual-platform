// 贪吃蛇（暖阳像素版：金色时刻 · 温暖正面 · 真·像素渲染 + 柔和音效——双端统一单源）
    var Snake = (function () {
      var N = 24, CELL = 5, PXW = N * CELL, PXH = N * CELL;  // 120×120 真·像素
      var canvas, ctx, px, pctx, shown = 0;
      var snake = [], prev = [], dir = { x: 1, y: 0 }, queue = [];
      var food = { x: 14, y: 12 }, bonus = null, bonusIn = 5;
      var score = 0, best = 0, stepMs = 150;
      var state = 'start';   // start | play | pause | dead
      var acc = 0, lastTs = 0, rafId = 0;
      var pulse = 0, particles = [], floaters = [], shake = 0, flash = 0;
      var clouds = [], flies = [], apples = 0;
      var muted = false, actx = null;

      function el(id) { return document.getElementById(id); }

      // ═══ 柔和音效（C 大调五声音阶——温暖正面；可静音） ═══
      var PENTA = [523.25, 587.33, 659.25, 783.99, 880.0];
      function audio() {
        if (muted) return null;
        if (!actx) { try { actx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { return null; } }
        if (actx.state === 'suspended') { try { actx.resume(); } catch (e) { } }
        return actx;
      }
      function tone(freq, dur, vol, delay, slide) {
        var a = audio(); if (!a) return;
        var t0 = a.currentTime + (delay || 0);
        var o = a.createOscillator(), g = a.createGain();
        o.type = 'triangle'; o.frequency.setValueAtTime(freq, t0);
        if (slide) o.frequency.exponentialRampToValueAtTime(slide, t0 + dur);
        g.gain.setValueAtTime(vol || 0.05, t0);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        o.connect(g); g.connect(a.destination); o.start(t0); o.stop(t0 + dur + 0.02);
      }
      function sfxEat() { tone(PENTA[apples % PENTA.length], 0.12, 0.05); }
      function sfxBonus() { tone(523.25, 0.09, 0.05); tone(659.25, 0.09, 0.05, 0.08); tone(783.99, 0.14, 0.05, 0.16); }
      function sfxDie() { tone(440, 0.3, 0.055, 0, 293.66); tone(329.63, 0.3, 0.04, 0.12, 220); }
      function sfxRecord() { tone(523.25, 0.1, 0.05); tone(659.25, 0.1, 0.05, 0.1); tone(783.99, 0.1, 0.05, 0.2); tone(1046.5, 0.2, 0.05, 0.3); }

      function open() {
        canvas = el('snakeCanvas');
        ctx = canvas.getContext('2d');
        el('snakeOverlay').style.display = 'flex';
        var stage = canvas.parentElement;
        shown = Math.min(stage.clientWidth || 480, 500) || 480;
        canvas.style.width = shown + 'px';
        canvas.style.height = shown + 'px';
        canvas.width = shown; canvas.height = shown;
        if (!px) {
          px = document.createElement('canvas');
          px.width = PXW; px.height = PXH;
          pctx = px.getContext('2d');
        }
        muted = false;
        try { muted = localStorage.getItem('snakeMuted') === '1'; } catch (e) { }
        el('snakeSound').textContent = muted ? '🔇' : '🔊';
        initAtmosphere();
        loadBest(); reset(); setState('start');
        lastTs = 0; acc = 0;
        if (!rafId) rafId = requestAnimationFrame(loop);
      }
      function close() {
        if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
        el('snakeOverlay').style.display = 'none';
      }
      function reset() {
        var mid = (N / 2) | 0;
        snake = [{ x: 7, y: mid }, { x: 6, y: mid }, { x: 5, y: mid }];
        prev = snake.map(function (c) { return { x: c.x, y: c.y }; });
        dir = { x: 1, y: 0 }; queue = [];
        score = 0; stepMs = 150; acc = 0; particles = []; floaters = [];
        shake = 0; flash = 0; apples = 0; bonus = null; bonusIn = 5;
        placeFood(); updScore(false);
      }
      function freeCell() {
        var free = [];
        for (var x = 0; x < N; x++) for (var y = 0; y < N; y++) {
          var taken = snake.some(function (c) { return c.x === x && c.y === y; });
          if (!taken && food.x === x && food.y === y) taken = true;
          if (bonus && bonus.x === x && bonus.y === y) taken = true;
          if (!taken) free.push({ x: x, y: y });
        }
        return free.length ? free[(Math.random() * free.length) | 0] : null;
      }
      function placeFood() { var c = freeCell(); if (c) food = c; }

      function updScore(pop) {
        el('snakeScore').textContent = String(score);
        if (pop) {
          var b = el('snakeScore');
          b.classList.remove('pop'); void b.offsetWidth; b.classList.add('pop');
        }
        if (score > best) {
          best = score;
          try { localStorage.setItem('snakeBest', String(best)); } catch (e) { }
        }
        el('snakeBest').textContent = String(best);
      }
      function loadBest() {
        try { best = parseInt(localStorage.getItem('snakeBest') || '0', 10) || 0; } catch (e) { best = 0; }
        el('snakeBest').textContent = String(best);
      }

      // ═══ 状态机（温暖正面文案） ═══
      function setState(s) {
        state = s;
        var veil = el('snakeVeil');
        if (s === 'play') { veil.style.display = 'none'; return; }
        veil.style.display = 'flex';
        var em = el('veilEmoji'), t = el('veilTitle'), sub = el('veilSub'), btn = el('veilBtn');
        if (s === 'start') {
          em.textContent = '🌞';
          t.textContent = '准备好出发了吗？';
          sub.textContent = '方向键 / WASD / 滑动 · 一路收集阳光果';
          btn.textContent = '出发';
        } else if (s === 'pause') {
          em.textContent = '🌤';
          t.textContent = '歇一会儿';
          sub.textContent = '回来继续这段旅程吧';
          btn.textContent = '继续';
        } else {
          var record = score >= best && score > 0;
          if (record) {
            em.textContent = '🎉';
            t.textContent = '太棒了！新纪录 ' + score + ' 分';
            sub.textContent = '你越来越厉害了，继续挑战？';
            btn.textContent = '继续挑战';
          } else {
            em.textContent = '🌄';
            t.textContent = '这段旅程 · ' + score + ' 分';
            sub.textContent = '最高 ' + best + ' 分 · 再来一次，你可以的！';
            btn.textContent = '再来一次';
          }
        }
      }
      function begin() { reset(); setState('play'); acc = 0; lastTs = 0; }
      function togglePause() {
        if (state === 'play') setState('pause');
        else if (state === 'pause') setState('play');
        else begin();
      }
      function die() {
        state = 'dead'; shake = 9; flash = 6;
        for (var i = 0; i < snake.length; i++) {
          var c = snake[i];
          particles.push({ x: (c.x + 0.5) * CELL, y: (c.y + 0.5) * CELL,
            vx: (Math.random() - 0.5) * 0.12, vy: -Math.random() * 0.1,
            life: 500 + Math.random() * 300, max: 800,
            color: i === 0 ? '#FFF0C4' : '#FFCF6E', r: 2 });
        }
        sfxDie(); updScore(false); setState('dead');
      }

      // ═══ 主循环 ═══
      function loop(ts) {
        rafId = requestAnimationFrame(loop);
        if (!lastTs) lastTs = ts;
        var dt = Math.min(ts - lastTs, 100); lastTs = dt > 0 ? ts : lastTs;
        pulse += dt / 1000;
        if (shake > 0) shake = Math.max(0, shake - dt / 26);
        if (flash > 0) flash = Math.max(0, flash - dt / 40);
        updParticles(dt);
        updAtmosphere(dt);
        if (state === 'play') {
          acc += dt;
          while (acc >= stepMs) {
            acc -= stepMs;
            step();
            if (state !== 'play') { acc = 0; break; }
          }
        }
        render(dt);
      }

      function step() {
        while (queue.length) {
          var d = queue.shift();
          if (!(d.x === -dir.x && d.y === -dir.y) && !(d.x === dir.x && d.y === dir.y)) { dir = d; break; }
        }
        prev = snake.map(function (c) { return { x: c.x, y: c.y }; });
        var head = { x: snake[0].x + dir.x, y: snake[0].y + dir.y };
        if (head.x < 0 || head.y < 0 || head.x >= N || head.y >= N ||
            snake.some(function (c) { return c.x === head.x && c.y === head.y; })) { die(); return; }
        snake.unshift(head);
        var grew = false;
        if (head.x === food.x && head.y === food.y) {
          score += 10; apples++; grew = true;
          burst(food, ['#FFD447', '#FF9E5E', '#FFF0C4']);
          floaters.push({ text: '+10', x: (food.x + 0.5) * CELL, y: food.y * CELL, life: 900 });
          sfxEat(); placeFood();
          if (--bonusIn <= 0 && !bonus) {
            var c = freeCell(); if (c) { bonus = { x: c.x, y: c.y, ttl: 40 }; bonusIn = 5; }
            sfxBonus();
          }
          if (stepMs > 70) stepMs -= 3;
        }
        if (bonus) {
          bonus.ttl--;
          if (bonus.x === head.x && bonus.y === head.y) {
            score += 50; grew = true;
            burst(bonus, ['#FFD447', '#FFF6DE']);
            floaters.push({ text: '+50', x: (bonus.x + 0.5) * CELL, y: bonus.y * CELL, life: 1000 });
            sfxBonus(); bonus = null;
          } else if (bonus.ttl <= 0) { bonus = null; }
        }
        if (!grew) snake.pop();
        else prev.unshift(prev[0]);
        updScore(false);
      }

      // ═══ 氛围（云 / 萤火虫 / 阳光） ═══
      function initAtmosphere() {
        clouds = [
          { x: PXW * 0.15, y: 12, s: 0.0035, w: 22 },
          { x: PXW * 0.55, y: 26, s: 0.0025, w: 30 },
          { x: PXW * 0.85, y: 6, s: 0.0045, w: 18 },
        ];
        flies = [];
        for (var i = 0; i < 7; i++)
          flies.push({ x: Math.random() * PXW, y: PXH * 0.35 + Math.random() * PXH * 0.6,
            ph: Math.random() * 6.28, sp: 0.008 + Math.random() * 0.01 });
      }
      function updAtmosphere(dt) {
        for (var i = 0; i < clouds.length; i++) {
          clouds[i].x -= clouds[i].s * dt;
          if (clouds[i].x < -clouds[i].w - 10) clouds[i].x = PXW + 8;
        }
        for (var j = 0; j < flies.length; j++) {
          var fl = flies[j];
          fl.y -= fl.sp * dt; fl.ph += dt / 600;
          fl.x += Math.sin(fl.ph) * 0.06;
          if (fl.y < 4) fl.y = PXH - 4;
        }
      }

      // ═══ 粒子 ═══
      function burst(cell, colors) {
        var cx = (cell.x + 0.5) * CELL, cy = (cell.y + 0.5) * CELL;
        for (var i = 0; i < 14; i++) {
          var a = Math.random() * 6.283, sp = 0.03 + Math.random() * 0.1;
          particles.push({ x: cx, y: cy, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 0.02,
            life: 460 + Math.random() * 240, max: 700,
            color: colors[(Math.random() * colors.length) | 0], r: 1 + Math.random() * 1.6 });
        }
      }
      function updParticles(dt) {
        for (var i = particles.length - 1; i >= 0; i--) {
          var p = particles[i];
          p.x += p.vx * dt; p.y += p.vy * dt;
          p.vy += 0.00012 * dt;
          p.life -= dt;
          if (p.life <= 0) particles.splice(i, 1);
        }
      }

      // ═══ 像素数字（3×5 位图）═══
      var DIG = { '0': [7,5,5,5,7], '1': [2,6,2,2,7], '2': [7,1,7,4,7], '3': [7,1,7,1,7],
        '4': [5,5,7,1,1], '5': [7,4,7,1,7], '6': [7,4,7,5,7], '7': [7,1,2,2,2],
        '8': [7,5,7,5,7], '9': [7,5,7,1,7], '+': [0,2,7,2,0] };
      function drawPixelText(str, x, y, color) {
        pctx.fillStyle = color;
        var cx0 = x - str.length * 2;
        for (var c = 0; c < str.length; c++) {
          var glyph = DIG[str[c]]; if (!glyph) continue;
          for (var r = 0; r < 5; r++) {
            var bits = glyph[r];
            for (var b = 0; b < 3; b++)
              if (bits & (4 >> b)) pctx.fillRect(cx0 + c * 4 + b, y + r, 1, 1);
          }
        }
      }

      // ═══ 像素精灵 ═══
      var APPLE = [ // [dx,dy,color] —— 苹果（暖红 + 高光 + 绿叶）
        [2,0,'#7A9E4E'],[3,0,'#8FBF5E'],
        [1,1,'#FFD9C4'],[2,1,'#E85D4A'],[3,1,'#E85D4A'],
        [0,2,'#E85D4A'],[1,2,'#E85D4A'],[2,2,'#E85D4A'],[3,2,'#E85D4A'],[4,2,'#E85D4A'],
        [1,3,'#E85D4A'],[2,3,'#C23F2F'],[3,3,'#C23F2F'],[4,3,'#C23F2F'],
        [2,4,'#C23F2F']];
      var STAR = [ // 金色星（奖励）
        [2,0,'#FFD447'],[1,1,'#FFD447'],[2,1,'#FFF6DE'],[3,1,'#FFD447'],
        [0,2,'#FFD447'],[1,2,'#FFD447'],[2,2,'#FFF6DE'],[3,2,'#FFD447'],[4,2,'#FFD447'],
        [1,3,'#FFD447'],[2,3,'#FFD447'],[3,3,'#FFD447'],[2,4,'#FFD447']];

      // ═══ 渲染（暖阳像素：日落天空 / 蜜金蛇 / 萤火虫） ═══
      function render(dt) {
        var t = state === 'play' ? Math.min(acc / stepMs, 1) : 1;
        pctx.save();
        if (shake > 0) pctx.translate((Math.random() - 0.5) * shake * 0.6, (Math.random() - 0.5) * shake * 0.6);
        // 暖阳天空（杏 → 琥珀 → 玫瑰）
        var sky = pctx.createLinearGradient(0, 0, 0, PXH);
        sky.addColorStop(0, '#FFE9C4'); sky.addColorStop(0.55, '#FFCE8A'); sky.addColorStop(1, '#F5A983');
        pctx.fillStyle = sky; pctx.fillRect(0, 0, PXW, PXH);
        // 太阳 + 光晕
        pctx.fillStyle = 'rgba(255,246,222,0.35)';
        pctx.beginPath(); pctx.arc(PXW * 0.78, PXH * 0.22, 16, 0, 7); pctx.fill();
        pctx.fillStyle = '#FFF6DE';
        pctx.beginPath(); pctx.arc(PXW * 0.78, PXH * 0.22, 9, 0, 7); pctx.fill();
        // 斜射暖光带（呼吸）
        pctx.fillStyle = 'rgba(255,243,214,' + (0.05 + 0.03 * Math.sin(pulse * 1.2)) + ')';
        pctx.beginPath(); pctx.moveTo(PXW * 0.7, 0); pctx.lineTo(PXW, 0);
        pctx.lineTo(PXW * 0.45, PXH); pctx.lineTo(PXW * 0.2, PXH); pctx.closePath(); pctx.fill();
        // 像素云（缓慢漂移）
        for (var ci = 0; ci < clouds.length; ci++) {
          var cl = clouds[ci];
          pctx.fillStyle = 'rgba(255,250,240,0.85)';
          pctx.fillRect(cl.x, cl.y, cl.w, 4);
          pctx.fillRect(cl.x + cl.w * 0.2, cl.y - 3, cl.w * 0.5, 3);
          pctx.fillStyle = 'rgba(255,233,196,0.9)';
          pctx.fillRect(cl.x + 2, cl.y + 4, cl.w - 4, 2);
        }
        // 暖色棋盘微纹理（可读性）
        pctx.fillStyle = 'rgba(255,255,255,0.05)';
        for (var cx2 = 0; cx2 < N; cx2++) for (var cy2 = 0; cy2 < N; cy2++)
          if ((cx2 + cy2) % 2 === 0) pctx.fillRect(cx2 * CELL, cy2 * CELL, CELL, CELL);
        // 萤火虫（漂浮暖光）
        for (var fi = 0; fi < flies.length; fi++) {
          var fl = flies[fi];
          var a = 0.35 + 0.3 * Math.sin(pulse * 3 + fl.ph * 4);
          pctx.fillStyle = 'rgba(255,233,168,' + a.toFixed(2) + ')';
          pctx.fillRect(fl.x | 0, fl.y | 0, 1, 1);
        }
        // 苹果 / 奖励星（像素精灵）
        drawSprite(APPLE, food.x * CELL, food.y * CELL);
        if (bonus && (bonus.ttl > 10 || (pulse * 4 | 0) % 2 === 0))
          drawSprite(STAR, bonus.x * CELL, bonus.y * CELL);
        // 蛇（蜜金：暗描边 + 渐变亮身，插值）
        var pts = snake.map(function (c, i) {
          var p = prev[i] || prev[prev.length - 1] || c;
          return { x: Math.round((p.x + (c.x - p.x) * t) * CELL), y: Math.round((p.y + (c.y - p.y) * t) * CELL) };
        });
        if (pts.length > 1) {
          pctx.lineJoin = 'round'; pctx.lineCap = 'round';
          pctx.strokeStyle = '#B87A1E'; pctx.lineWidth = CELL;
          pctx.beginPath(); pctx.moveTo(pts[0].x + 2.5, pts[0].y + 2.5);
          for (var i2 = 1; i2 < pts.length; i2++) pctx.lineTo(pts[i2].x + 2.5, pts[i2].y + 2.5);
          pctx.stroke();
          var g = pctx.createLinearGradient(pts[0].x, pts[0].y, pts[pts.length - 1].x, pts[pts.length - 1].y);
          g.addColorStop(0, '#FFE9A8'); g.addColorStop(1, '#E8A93C');
          pctx.strokeStyle = g; pctx.lineWidth = CELL - 1;
          pctx.stroke();
        }
        // 头（亮蜜色 + 暖色眼睛）
        var h = pts[0];
        pctx.fillStyle = '#FFF0C4'; pctx.fillRect(h.x, h.y, CELL, CELL);
        pctx.fillStyle = '#5A3A10';
        var ex = dir.y !== 0 ? 1 : 0, ey = dir.x !== 0 ? 1 : 0;
        pctx.fillRect(h.x + 1 + ex, h.y + 1 + ey, 1, 1);
        pctx.fillRect(h.x + 3 - ey, h.y + 3 - ex, 1, 1);
        // 粒子
        for (var i3 = 0; i3 < particles.length; i3++) {
          var p2 = particles[i3];
          pctx.globalAlpha = Math.max(0, p2.life / p2.max);
          pctx.fillStyle = p2.color;
          pctx.fillRect(p2.x | 0, p2.y | 0, p2.r, p2.r);
        }
        pctx.globalAlpha = 1;
        // 浮动得分（像素数字）
        for (var i4 = floaters.length - 1; i4 >= 0; i4--) {
          var fo = floaters[i4];
          fo.life -= dt; fo.y -= dt * 0.016;
          if (fo.life <= 0) { floaters.splice(i4, 1); continue; }
          pctx.globalAlpha = Math.min(1, fo.life / 500);
          drawPixelText(fo.text, fo.x, fo.y | 0, '#FFF6E3');
        }
        pctx.globalAlpha = 1;
        // 死亡暖红闪
        if (flash > 0) { pctx.fillStyle = 'rgba(255,120,80,' + (flash / 40).toFixed(2) + ')'; pctx.fillRect(0, 0, PXW, PXH); }
        pctx.restore();
        // 放大到显示画布（关平滑——真·像素）
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(px, 0, 0, PXW, PXH, 0, 0, canvas.width, canvas.height);
      }
      function drawSprite(sp, ox, oy) {
        for (var i = 0; i < sp.length; i++) {
          pctx.fillStyle = sp[i][2];
          pctx.fillRect(ox + sp[i][0], oy + sp[i][1], 1, 1);
        }
      }

      // ═══ 输入 ═══
      function turn(x, y) {
        var last = queue.length ? queue[queue.length - 1] : dir;
        if (x === -last.x && y === -last.y) return;
        if (x === last.x && y === last.y) return;
        if (queue.length < 3) queue.push({ x: x, y: y });
      }
      function primaryAction() {
        if (state === 'play') setState('pause');
        else if (state === 'pause') setState('play');
        else begin();
      }
      document.addEventListener('keydown', function (e) {
        var ov = el('snakeOverlay');
        if (!ov || ov.style.display === 'none') return;
        var k = e.key;
        if (k === 'ArrowUp' || k === 'w' || k === 'W') { turn(0, -1); e.preventDefault(); }
        else if (k === 'ArrowDown' || k === 's' || k === 'S') { turn(0, 1); e.preventDefault(); }
        else if (k === 'ArrowLeft' || k === 'a' || k === 'A') { turn(-1, 0); e.preventDefault(); }
        else if (k === 'ArrowRight' || k === 'd' || k === 'D') { turn(1, 0); e.preventDefault(); }
        else if (k === ' ') { primaryAction(); e.preventDefault(); }
        else if (k === 'Escape') { close(); e.preventDefault(); }
      });
      (function () {
        var sx = 0, sy = 0, on = false;
        document.addEventListener('touchstart', function (e) {
          var ov = el('snakeOverlay');
          if (!ov || ov.style.display === 'none') return;
          if (e.target && e.target.id !== 'snakeCanvas') return;
          sx = e.touches[0].clientX; sy = e.touches[0].clientY; on = true;
        }, { passive: true });
        document.addEventListener('touchmove', function (e) { if (on) e.preventDefault(); }, { passive: false });
        document.addEventListener('touchend', function (e) {
          if (!on) return; on = false;
          var dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
          if (Math.abs(dx) < 18 && Math.abs(dy) < 18) { primaryAction(); return; }
          if (Math.abs(dx) > Math.abs(dy)) turn(dx > 0 ? 1 : -1, 0);
          else turn(0, dy > 0 ? 1 : -1);
        });
      })();
      document.addEventListener('DOMContentLoaded', function () {
        var btn = el('veilBtn');
        if (btn) btn.addEventListener('click', function (ev) { ev.stopPropagation(); primaryAction(); });
        var cv = el('snakeCanvas');
        if (cv) cv.addEventListener('click', function () { primaryAction(); });
        var snd = el('snakeSound');
        if (snd) snd.addEventListener('click', function (ev) {
          ev.stopPropagation();
          muted = !muted;
          try { localStorage.setItem('snakeMuted', muted ? '1' : '0'); } catch (e) { }
          el('snakeSound').textContent = muted ? '🔇' : '🔊';
        });
      });

      return { open: open, close: close };
    })();

    function openSnake() { if (Host.has('snake')) Snake.open(); }