// 贪吃蛇（首页内置——双端统一；ADR-007 单源）
    var Snake = (function () {
      var N = 20, CELL, ctx, timer = null, running = false, paused = false;
      var snake, dir, nextDir, food, score, speed, shown = 360, best = 0;

      function open() {
        var cv = document.getElementById('snakeCanvas');
        ctx = cv.getContext('2d');
        var dpr = window.devicePixelRatio || 1;
        shown = Math.min(cv.clientWidth || 360, 360) || 360;
        cv.width = shown * dpr; cv.height = shown * dpr;
        ctx = cv.getContext('2d');
        ctx.scale(dpr, dpr); CELL = shown / N;
        document.getElementById('snakeOverlay').style.display = 'flex';
        loadBest(); reset(); start();
      }
      function close() {
        stop();
        document.getElementById('snakeOverlay').style.display = 'none';
      }
      function reset() {
        snake = [{x:6,y:10},{x:5,y:10},{x:4,y:10}];  // 出生点偏左——右侧跑道充足，反应时间充裕
        dir = {x:1,y:0}; nextDir = dir; score = 0; speed = 170;
        placeFood(); updScore(); draw(false);
      }
      function placeFood() {
        do { food = { x: (Math.random()*N)|0, y: (Math.random()*N)|0 }; }
        while (snake.some(function (c) { return c.x===food.x && c.y===food.y; }));
      }
      function updScore() {
        document.getElementById('snakeScore').textContent = String(score);
        if (score > best) {
          best = score;
          try { localStorage.setItem('snakeBest', String(best)); } catch (e) { /* file:// 下可能禁用——降级内存 */ }
          document.getElementById('snakeBest').textContent = '最高 ' + best;
        }
      }
      function loadBest() {
        try { best = parseInt(localStorage.getItem('snakeBest') || '0', 10) || 0; } catch (e) { best = 0; }
        document.getElementById('snakeBest').textContent = '最高 ' + best;
      }
      function start() {
        stop(); running = true; paused = false;
        timer = setInterval(step, speed);
      }
      function stop() { if (timer) { clearInterval(timer); timer = null; } running = false; }
      function step() {
        if (paused || !running) return;
        dir = nextDir;
        var head = { x: snake[0].x + dir.x, y: snake[0].y + dir.y };
        if (head.x < 0 || head.y < 0 || head.x >= N || head.y >= N ||
            snake.some(function (c) { return c.x===head.x && c.y===head.y; })) {
          stop(); draw(true); return;   // 撞墙/撞身：定格显示
        }
        snake.unshift(head);
        if (head.x === food.x && head.y === food.y) {
          score += 10; updScore(); placeFood();
          if (speed > 70) { speed -= 4; stop(); start(); }  // 提速（重设 interval）
        } else {
          snake.pop();
        }
        draw(false);
      }
      function draw(dead) {
        ctx.fillStyle = '#0B1B14'; ctx.fillRect(0, 0, shown, shown);
        ctx.strokeStyle = 'rgba(29,58,46,0.9)'; ctx.lineWidth = 1;
        for (var i = 1; i < N; i++) {
          ctx.beginPath(); ctx.moveTo(i*CELL, 0); ctx.lineTo(i*CELL, shown); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(0, i*CELL); ctx.lineTo(shown, i*CELL); ctx.stroke();
        }
        ctx.fillStyle = '#FF5252';
        ctx.beginPath();
        ctx.arc(food.x*CELL + CELL/2, food.y*CELL + CELL/2, CELL*0.36, 0, 7);
        ctx.fill();
        snake.forEach(function (c, i) {
          ctx.fillStyle = i === 0 ? '#8BC34A' : '#4CAF50';
          ctx.fillRect(c.x*CELL + 1, c.y*CELL + 1, CELL - 2, CELL - 2);
        });
        if (dead) {
          ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillRect(0, 0, shown, shown);
          ctx.fillStyle = '#fff'; ctx.textAlign = 'center';
          ctx.font = 'bold 22px sans-serif';
          ctx.fillText('游戏结束 · 得分 ' + score, shown/2, shown/2 - 8);
          ctx.font = '13px sans-serif'; ctx.fillStyle = '#B9E4C7';
          ctx.fillText('按空格或点击画布再来一局', shown/2, shown/2 + 18);
        }
      }
      function turn(x, y) {
        if (x === -dir.x && y === -dir.y) return;  // 禁止 180° 掉头
        nextDir = { x: x, y: y };
      }
      function togglePause() { if (running) paused = !paused; }

      // 键盘（桌面端）
      document.addEventListener('keydown', function (e) {
        var ov = document.getElementById('snakeOverlay');
        if (!ov || ov.style.display === 'none') return;
        var k = e.key;
        if (k === 'ArrowUp' || k === 'w' || k === 'W') { turn(0,-1); e.preventDefault(); }
        else if (k === 'ArrowDown' || k === 's' || k === 'S') { turn(0,1); e.preventDefault(); }
        else if (k === 'ArrowLeft' || k === 'a' || k === 'A') { turn(-1,0); e.preventDefault(); }
        else if (k === 'ArrowRight' || k === 'd' || k === 'D') { turn(1,0); e.preventDefault(); }
        else if (k === ' ') {
          if (!running) { reset(); start(); } else togglePause();
          e.preventDefault();
        }
      });
      // 滑动手势（移动端）
      (function () {
        var sx = 0, sy = 0, on = false;
        var el = document.getElementById('snakeCanvas');
        el.addEventListener('touchstart', function (e) {
          sx = e.touches[0].clientX; sy = e.touches[0].clientY; on = true;
        }, { passive: true });
        el.addEventListener('touchmove', function (e) { e.preventDefault(); }, { passive: false });
        el.addEventListener('touchend', function (e) {
          if (!on) return; on = false;
          var dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
          if (Math.abs(dx) < 18 && Math.abs(dy) < 18) {   // 轻点：死亡后重开
            if (!running && !timer) { reset(); start(); }
            return;
          }
          if (Math.abs(dx) > Math.abs(dy)) turn(dx > 0 ? 1 : -1, 0);
          else turn(0, dy > 0 ? 1 : -1);
        });
        el.addEventListener('click', function () {
          if (!running && !timer) { reset(); start(); }
        });
      })();

      return { open: open, close: close };
    })();

    function openSnake() { if (Host.has('snake')) Snake.open(); }
