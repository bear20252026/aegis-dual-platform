// 导入向导（Chrome/Edge 书签与历史；ADR-007 单源）
    // 受信壳页专用——桥方法内再做来源校验（远程页不可达）。
    // R-06：全部 DOM 以 textContent/replaceChildren 构建（无 innerHTML）。
    (function () {
      var modal = document.getElementById('importModal');
      var body = document.getElementById('imBody');
      var nextBtn = document.getElementById('imNext');
      var closeBtn = document.getElementById('imClose');
      var entry = document.getElementById('importEntry');
      if (!modal || !body || !nextBtn || !closeBtn || !entry) return;

      var sources = [];      // scan_import_sources() 结果
    // Android 宿主无导入能力——隐藏入口（Host.has 能力面声明）
    if (!Host.has('import')) entry.style.display = 'none';
      var step = 'pick';     // pick | running | done
      var pickedChecks = []; // 来源复选框（.browser）
      var bmCheck = null, hiCheck = null, limitSel = null;

      function api() { return Host; }
      function label(b) { return b === 'chrome' ? 'Chrome' : 'Edge'; }

      function close() {
        modal.style.display = 'none';
        body.textContent = '';
        step = 'pick';
        nextBtn.disabled = false;
      }

      function checkboxRow(text, checked) {
        var row = document.createElement('label');
        row.className = 'im-row';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = !!checked;
        var txt = document.createElement('span');
        txt.textContent = text;
        row.appendChild(cb);
        row.appendChild(txt);
        row._cb = cb;
        return row;
      }

      function hint(text) {
        var d = document.createElement('div');
        d.className = 'im-empty';
        d.textContent = text;
        return d;
      }

      function renderPick() {
        body.textContent = '';
        step = 'pick';
        if (!sources.length) {
          nextBtn.style.display = 'none';
          body.appendChild(hint('未检测到 Chrome / Edge 数据（仅支持 Default 配置目录）。'));
          return;
        }
        nextBtn.style.display = '';
        nextBtn.textContent = '开始导入';
        var sec = document.createElement('div');
        sec.className = 'im-section';
        sec.textContent = '检测到以下来源：';
        body.appendChild(sec);
        pickedChecks = [];
        sources.forEach(function (s, i) {
          var parts = [];
          if (s.bookmarks) parts.push('书签');
          if (s.history) parts.push('历史');
          var row = checkboxRow(label(s.browser) + '（' + parts.join(' + ') + '）', i === 0);
          row._browser = s.browser;
          pickedChecks.push(row);
          body.appendChild(row);
        });
        var sec2 = document.createElement('div');
        sec2.className = 'im-section';
        sec2.textContent = '导入内容：';
        body.appendChild(sec2);
        var bmRow = checkboxRow('书签', true);
        bmCheck = bmRow._cb;
        body.appendChild(bmRow);
        var hiRow = checkboxRow('历史（最近）', true);
        hiCheck = hiRow._cb;
        body.appendChild(hiRow);
        var limRow = document.createElement('div');
        limRow.className = 'im-row';
        var limText = document.createElement('span');
        limText.textContent = '历史条数上限：';
        limitSel = document.createElement('select');
        [100, 500, 1000, 2000].forEach(function (n) {
          var o = document.createElement('option');
          o.value = String(n);
          o.textContent = String(n);
          if (n === 500) o.selected = true;
          limitSel.appendChild(o);
        });
        limRow.appendChild(limText);
        limRow.appendChild(limitSel);
        body.appendChild(limRow);
      }

      function collect(kind, browser, r) {
        r = r || {};
        var imp = parseInt(r.imported, 10) || 0;
        var tot = parseInt(r.total, 10) || 0;
        agg.imported += imp;
        agg.total += tot;
        agg.lines.push(label(browser) + ' ' + kind + '：导入 ' + imp + ' / ' + tot);
      }

      var agg = { imported: 0, total: 0, lines: [] };

      function runImport() {
        var picked = [];
        pickedChecks.forEach(function (row) {
          if (row._cb.checked) picked.push(row._browser);
        });
        var doBm = !!(bmCheck && bmCheck.checked);
        var doHi = !!(hiCheck && hiCheck.checked);
        if (!picked.length || (!doBm && !doHi)) { close(); return; }
        var a = api();
        if (!a) { close(); return; }
        step = 'running';
        nextBtn.disabled = true;
        body.textContent = '';
        body.appendChild(hint('正在导入…（浏览器数据库只读访问，不影响源浏览器）'));
        var lim = parseInt(limitSel ? limitSel.value : '500', 10) || 500;
        agg = { imported: 0, total: 0, lines: [] };
        var chain = Promise.resolve();
        picked.forEach(function (src) {
          if (doBm) {
            chain = chain.then(function () { return a.importBookmarks(src); })
              .then(function (r) { collect('书签', src, r); });
          }
          if (doHi) {
            chain = chain.then(function () { return a.importHistory(lim, src, function () {}); })
              .then(function (r) { collect('历史', src, r); });
          }
        });
        chain.then(renderDone).catch(renderDone);
      }

      function renderDone() {
        body.textContent = '';
        step = 'done';
        nextBtn.disabled = false;
        nextBtn.textContent = '完成';
        var sum = document.createElement('div');
        sum.className = 'im-result';
        sum.textContent = '导入完成：共新增 ' + agg.imported + ' 条（解析 ' + agg.total + ' 条）。';
        body.appendChild(sum);
        agg.lines.forEach(function (line) {
          var d = document.createElement('div');
          d.className = 'im-result';
          d.textContent = '· ' + line;
          body.appendChild(d);
        });
        if (agg.imported > 0 && typeof renderBookmarks === 'function') {
          renderBookmarks();  // 刷新宫格
        }
      }

      function openWizard() {
        var a = api();
        if (!a) return;
        modal.style.display = 'flex';
        body.textContent = '';
        step = 'pick';
        nextBtn.disabled = true;
        nextBtn.textContent = '扫描中…';
        nextBtn.style.display = '';
        body.appendChild(hint('正在扫描本机 Chrome / Edge 数据…'));
        try {
          Host.importScan(function (list) {
            sources = Array.isArray(list) ? list : [];
            nextBtn.disabled = false;
            renderPick();
          }).catch(function () {
            sources = [];
            nextBtn.disabled = false;
            renderPick();
          });
        } catch (e) {
          sources = [];
          nextBtn.disabled = false;
          renderPick();
        }
      }

      entry.addEventListener('click', openWizard);
      closeBtn.addEventListener('click', close);
      nextBtn.addEventListener('click', function () {
        if (step === 'pick') runImport();
        else if (step === 'done') close();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.style.display !== 'none') close();
      });
    })();
