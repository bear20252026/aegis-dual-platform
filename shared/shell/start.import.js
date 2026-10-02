// 导入向导（Chrome/Edge 书签与历史；ADR-007 单源）
    // 受信壳页专用——桥方法内再做来源校验（远程页不可达）。
    // R-06：全部 DOM 以 textContent/replaceChildren 构建（无 innerHTML）。
    // WB-041（审计 2026-09-23 清单·W5 批）：补 'use strict'（此前与
    // start.snake.js 同为脚本外置时未声明严格模式的两个文件）
    'use strict';
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
      var lastFocus = null;  // 打开向导前的焦点元素（关闭时归还——WB-027）

      function api() { return Host; }
      function label(b) { return b === 'chrome' ? 'Chrome' : 'Edge'; }

      function close() {
        // WB-176（2026-10-02 审计）：running 态关闭守卫——closeBtn click 路径
        // 此前无守卫（Escape 路径 WB-056 已挡）：导入进行中点击「关闭」即
        // 静默中断向导（桥任务照跑、结果丢弃且无提示）。与 Escape 语义对齐，
        // 并以 runImport/renderDone 的 closeBtn.disabled 作双保险
        if (step === 'running') return;
        // WB-179（2026-10-02 审计）：显隐改 hidden 属性配对翻转——此前压
        // 内联 style.display，hidden 属性残留（语义仍声明「隐藏」与视觉
        // 可见矛盾）。初始隐藏由标记层 hidden 承担，开/关必须配对
        modal.setAttribute('hidden', '');
        body.textContent = '';
        step = 'pick';
        nextBtn.disabled = false;
        // WB-027：焦点归还触发元素——键盘/读屏用户关闭弹层后回到原位，
        // 不再「焦点失踪」落到 body（Tab 从页首重来）
        try { if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus(); } catch (e) {}
        lastFocus = null;
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

      // WB-134（2026-10-01 审计）：提示节点单例——hint() 此前每次调用
      // 新建 div 直接 append（runImport 校验失败连点 N 次即堆 N 条同文
      // 提示不消散）。复用同一节点：textContent 换文案、appendChild 对
      // 已挂载节点是移动而非复制，天然不堆叠。
      var hintNode = null;
      function hint(text) {
        if (!hintNode) {
          hintNode = document.createElement('div');
          hintNode.className = 'im-empty';
        }
        hintNode.textContent = text;
        return hintNode;
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
        // WB-145（2026-10-01 审计）：下拉无可编程名称——读屏只播报裸
        // select 无语义；label 文案是平级 span 不构成表单关联
        limitSel.setAttribute('aria-label', '历史条数上限');
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
        // WB-055（审计 2026-09-23 清单·W5 批）：未选来源/内容此前静默
        // close()——用户以为点击失效或导入完成。改为留在选择页并给出
        // 明确提示（不重建页面、不丢已勾选状态）
        if (!picked.length || (!doBm && !doHi)) {
          body.appendChild(hint('请先选择至少一个导入来源与内容类型（书签/历史）。'));
          return;
        }
        var a = api();
        // WB-189（2026-10-02 审计）：删除恒假守卫 if(!a){close();return;}——
        // openWizard 入口已挡无桥形态，能走到此行则 Host 必在
        step = 'running';
        nextBtn.disabled = true;
        // WB-176：running 态关闭钮同步禁用——视觉态与 close() 守卫一致
        closeBtn.disabled = true;
        body.textContent = '';
        body.appendChild(hint('正在导入…（浏览器数据库只读访问，不影响源浏览器）'));
        var lim = parseInt(limitSel ? limitSel.value : '500', 10) || 500;
        agg = { imported: 0, total: 0, lines: [] };
        var chain = Promise.resolve();
        var failures = 0;
        picked.forEach(function (src) {
          if (doBm) {
            chain = chain.then(function () { return a.importBookmarks(src); })
              .then(function (r) {
                // WB-136（2026-10-01 审计）：csCall TTL 兜底/null 回包此前经
                // collect 的 r||{} 计入「成功 0/0」——无响应被伪装成成功来源；
                // null/undefined 单列计入 failures
                if (r === null || r === undefined) { failures++; return; }
                collect('书签', src, r);
              })
              .catch(function () { failures++; });
          }
          if (doHi) {
            chain = chain.then(function () { return a.importHistory(lim, src); })
              .then(function (r) {
                if (r === null || r === undefined) { failures++; return; }  // WB-136
                collect('历史', src, r);
              })
              .catch(function () { failures++; });
          }
        });
        // WB-135（2026-10-01 审计）：导入总超时兜底——桥挂起（pending 永不
        // resolve 且无后续 csCall 触发 TTL 清扫）时向导此前永久停在
        // running 态（下一步禁用、Escape 被 WB-056 忽略）。约 60s 总超时后
        // 渲染失败态；时长消费 start.js 的 AegisTiming 单源（字面量兜底一致）
        var runSettled = false;
        var runTimeoutMs = (typeof window !== 'undefined' &&
          window.AegisTiming && window.AegisTiming.IMPORT_RUN_TIMEOUT_MS) || 60000;
        var runTimer = setTimeout(function () {
          if (runSettled || step !== 'running') return;
          runSettled = true;
          renderDone(failures + 1, true);
        }, runTimeoutMs);
        function runDone(failedCount) {
          if (runSettled) return;
          runSettled = true;
          clearTimeout(runTimer);
          renderDone(failedCount, false);
        }
        chain.then(function () { runDone(failures); })
          .catch(function () { runDone(failures + 1); });
      }

      function renderDone(failedCount, timedOut) {
        body.textContent = '';
        step = 'done';
        nextBtn.disabled = false;
        // WB-176：离开 running 态——关闭钮恢复可用
        closeBtn.disabled = false;
        nextBtn.textContent = '完成';
        var sum = document.createElement('div');
        sum.className = 'im-result';
        // 成功与失败不再渲染同一界面（此前 .then/.catch 同一 renderDone——
        // 失败被伪装成"导入完成"）；WB-135：timedOut=true 为总超时兜底路径
        if (failedCount > 0 && agg.imported === 0) {
          sum.textContent = timedOut
            ? '导入超时：' + failedCount + ' 个来源无响应（宿主长时间未返回结果），请确认浏览器状态后重试。'
            : '导入失败：' + failedCount + ' 个来源未能读取（浏览器可能正在运行或数据不可用）。';
        } else if (failedCount > 0) {
          sum.textContent = timedOut
            ? '部分完成（超时）：新增 ' + agg.imported + ' 条（解析 ' + agg.total + ' 条），' + failedCount + ' 个来源无响应。'
            : '部分完成：新增 ' + agg.imported + ' 条（解析 ' + agg.total + ' 条），' + failedCount + ' 个来源失败。';
        } else {
          sum.textContent = '导入完成：共新增 ' + agg.imported + ' 条（解析 ' + agg.total + ' 条）。';
        }
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
        // WB-027：记录触发元素（关闭时归还焦点）——必须在显示弹层前取
        try { lastFocus = document.activeElement || entry; } catch (e) { lastFocus = entry; }
        // WB-179：打开 = 移除 hidden 属性（与 close 的 setAttribute 配对
        // 翻转；[hidden] 高特异度 CSS 规则压过作者 display:flex——WB-126）
        modal.removeAttribute('hidden');
        body.textContent = '';
        step = 'pick';
        nextBtn.disabled = true;
        nextBtn.textContent = '扫描中…';
        nextBtn.style.display = '';
        body.appendChild(hint('正在扫描本机 Chrome / Edge 数据…'));
        // WB-027：初始焦点进弹层（aria-modal 弹层不接收焦点是读屏重大缺陷）——
        // closeBtn 常驻且无副作用，安全兜底
        try { closeBtn.focus(); } catch (e) {}
        // 扫描超时（15s）：宿主无响应（如桥未挂接的窗口）不再永久卡死向导
        // WB-057（审计 2026-09-23 清单·W5 批）：超时时长收敛到 start.js 的
        // window.AegisTiming.IMPORT_SCAN_TIMEOUT_MS 单源（字面量兜底一致）
        var scanSettled = false;
        var scanTimeoutMs = (typeof window !== 'undefined' &&
          window.AegisTiming && window.AegisTiming.IMPORT_SCAN_TIMEOUT_MS) || 15000;
        var scanTimer = setTimeout(function () {
          if (scanSettled) return;
          scanSettled = true;
          sources = [];
          nextBtn.disabled = false;
          renderPick();
        }, scanTimeoutMs);
        function scanDone(list) {
          if (scanSettled) return;
          scanSettled = true;
          clearTimeout(scanTimer);
          sources = Array.isArray(list) ? list : [];
          nextBtn.disabled = false;
          renderPick();
        }
        try {
          // 宿主返回形态不一（cs·android=同步回调 undefined；桥层若包装成
          // Promise 则可能拒绝）——统一走回调，绝不对可能为 undefined 的
          // 返回值调 .catch（WB-114：win 归档桥分支已删）
          var ret = Host.importScan(scanDone);
          if (ret && typeof ret.catch === 'function') ret.catch(function () { scanDone([]); });
        } catch (e) {
          scanDone([]);
        }
      }

      entry.addEventListener('click', openWizard);
      closeBtn.addEventListener('click', close);
      nextBtn.addEventListener('click', function () {
        if (step === 'pick') runImport();
        else if (step === 'done') close();
      });
      document.addEventListener('keydown', function (e) {
        // WB-056（审计 2026-09-23 清单·W5 批）：running 态 Escape 不再关闭——
        // 此前导入进行中按 Esc 静默中断向导（桥任务照跑、结果丢弃且无提示）。
        // running 期间忽略 Escape；pick/done 态维持即关
        // WB-179/204（2026-10-02 审计）：开态判定改 hidden 属性口径——旧
        // 「style.display !== 'none'」在未打开时恒真（内联 display 为空串），
        // Escape 恒执行 close 副作用；hidden 在未打开时存在 → 守卫恒假
        if (e.key === 'Escape' && !modal.hasAttribute('hidden')) {
          if (step === 'running') return;
          close();
        }
      });
      // WB-027：焦点陷阱——Tab/Shift+Tab 在弹层内循环，禁止逃逸到被
      // aria-modal 遮蔽的背景页（聚焦集合每次按键时实时收集，覆盖
      // 各步骤动态重建的复选框/下拉）
      modal.addEventListener('keydown', function (e) {
        // WB-179：同 Escape 口径——陷阱只应在开态接管 Tab
        if (e.key !== 'Tab' || modal.hasAttribute('hidden')) return;
        var items = [];
        try {
          var all = modal.querySelectorAll('button, input, select, [tabindex]');
          for (var i = 0; i < all.length; i++) {
            var it = all[i];
            if (it.disabled) continue;
            var st = null;
            try { st = it.style ? it.style.display : ''; } catch (e2) {}
            if (st === 'none') continue;
            items.push(it);
          }
        } catch (e3) { return; }
        if (!items.length) return;
        var first = items[0], last = items[items.length - 1];
        var active = document.activeElement;
        var inside = false;
        try { inside = !!active && modal.contains(active); } catch (e4) { inside = false; }
        if (e.shiftKey && (active === first || !inside)) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && (active === last || !inside)) {
          e.preventDefault(); first.focus();
        }
      });
    })();
