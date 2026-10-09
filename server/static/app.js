const API = '';

const app = {
  currentTab: 'discover',
  events: [],
  selectedEvent: null,
  holdings: [],
  notifications: [],
  subscriptions: [],
  preferences: { risk_level: 'moderate', notification_enabled: true },
  user: { id: 1, name: '测试用户', avatar: null },
  feedOffset: 0,
  feedLimit: 30,
  _loadingMore: false,
  _atEnd: false,
  feedTotal: 0,
  feedSearch: '',
  feedNature: '',
  feedStatus: '',
  feedFollowed: false,
  followedTickers: new Set(),
  chatHistory: [],

  async init() {
    this.bindNav();
    this.bindSearch();
    this.bindChat();
    this.bindFilters();
    this.bindRefresh();
    await this.loadTickers();      // 先拿关注标的，卡片才能显示「已关注」
    await Promise.all([
      this.loadEvents(),
      this.loadHoldings(),
      this.loadNotifications(),
      this.loadSubscriptions(),
      this.loadPreferences(),
    ]);
    console.log('[App] Initialized');
  },

  // ─── 轻提示 ───
  toast(msg, type = '', ms = 2600) {
    let box = document.getElementById('toast-box');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast-box';
      document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => {
      el.classList.add('hide');
      setTimeout(() => el.remove(), 320);
    }, ms);
  },

  async api(path, options = {}) {
    const opts = { headers: { 'Content-Type': 'application/json' }, ...options };
    if (opts.body && typeof opts.body === 'object') opts.body = JSON.stringify(opts.body);
    const res = await fetch(`${API}${path}`, opts);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
    }
    return res.json();
  },

  // ─── Nav ───
  bindNav() {
    document.querySelectorAll('.nav-item').forEach(btn =>
      btn.addEventListener('click', () => this.switchTab(btn.dataset.tab)));
  },

  switchTab(tab) {
    this.currentTab = tab;
    document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelector(`.nav-item[data-tab="${tab}"]`).classList.add('active');
    document.getElementById('page-title').textContent = { discover: '发现', advisor: '参谋', profile: '我的' }[tab];
    // 头部搜索框仅在「发现」页显示
    document.querySelector('.app-header').dataset.tab = tab;
    // 切到「我的」页时刷新关注列表
    if (tab === 'profile') this.loadSubscribedEvents();
  },

  // ─── Events Feed ───
  async loadEvents(append = false) {
    const list = document.getElementById('discover-list');
    const loadingBar = document.getElementById('feed-loading');
    if (!append) {
      this.feedOffset = 0;
      this._atEnd = false;
      this.events = [];
      const endBar = document.getElementById('feed-end');
      if (endBar) endBar.style.display = 'none';
      list.innerHTML = '<div class="loading">加载中...</div>';
    } else if (loadingBar) {
      loadingBar.style.display = 'block';
    }
    try {
      const params = new URLSearchParams();
      if (this.feedSearch) params.append('search', this.feedSearch);
      if (this.feedNature) params.append('nature', this.feedNature);
      if (this.feedStatus) params.append('status', this.feedStatus);
      if (this.feedFollowed) params.append('followed', '1');
      params.append('limit', this.feedLimit);
      params.append('offset', this.feedOffset);

      const data = await this.api(`/api/events?${params}`);
      const items = data.items || [];
      this.feedTotal = data.total || 0;
      if (data.status_counts) this.renderStatusCounts(data.status_counts);

      if (append) {
        this.events = this.events.concat(items);
      } else {
        this.events = items;
      }
      this.renderEvents(append ? items : this.events, append);
      document.getElementById('feed-count').textContent =
        `共 ${this.feedTotal} 个事件（已显示 ${this.events.length}）`;
      this.feedOffset = this.events.length;
    } catch (err) {
      if (!append) list.innerHTML = `<div class="empty-state">加载失败：${err.message}</div>`;
    } finally {
      if (loadingBar) loadingBar.style.display = 'none';
    }
  },

  renderEvents(events, append = false) {
    const list = document.getElementById('discover-list');
    if (!events.length && !append) {
      list.innerHTML = '<div class="empty-state">没有找到相关事件</div>';
      return;
    }
    const html = events.map(ev => this.eventCardHTML(ev)).join('');
    if (append) list.insertAdjacentHTML('beforeend', html);
    else list.innerHTML = html;
    list.querySelectorAll('.event-card').forEach(card =>
      card.addEventListener('click', () => this.openEventDetail(card.dataset.id)));
  },

  eventCardHTML(ev) {
    const tl = ev.timeline || [];
    const currentNode = tl.find(t => t.is_current) || tl[tl.length - 1] || {};
    // 同花顺惯例：红涨（利好）/ 绿跌（利空）；状态用独立色系
    const nb = {
      positive: { cls: 'badge-up', label: '利好' },
      negative: { cls: 'badge-down', label: '利空' },
      neutral: { cls: 'badge-gray', label: '中性' },
      risk: { cls: 'badge-orange', label: '风险' },
    }[ev.nature] || { cls: 'badge-gray', label: '中性' };
    const statusBadge = {
      '官方确认': 'badge-st-confirmed', '媒体验证': 'badge-st-media',
      '未证实传闻': 'badge-st-rumor', '官方否认': 'badge-st-denied',
      '实质落地': 'badge-st-landed', '已过期': 'badge-st-expired',
    }[ev.status] || 'badge-st-rumor';

    const dots = tl.map((t, i) => {
      const active = t.is_current ? 'active' : '';
      const line = i < tl.length - 1 ? '<div class="timeline-line"></div>' : '';
      return `<div class="timeline-dot ${active}"></div>${line}`;
    }).join('');

    const followed = (this.followedTickers && this.followedTickers.has(ev.ticker)) || ev.followed;

    return `
      <div class="event-card ${ev.nature}" data-id="${ev.id}">
        <div class="card-header">
          <div class="card-badges">
            <span class="badge ${nb.cls}">${nb.label}</span>
            <span class="badge ${statusBadge}">${ev.status}</span>
            ${followed ? '<span class="followed-tag">★ 已关注</span>' : ''}
          </div>
          <span style="font-size:11px;color:var(--text-3)">${ev.updated_at || ''}</span>
        </div>
        <div class="card-title">${ev.ticker_name} · ${ev.theme}</div>
        <div class="card-desc">${ev.headline}</div>
        <div class="card-timeline">${dots}<span class="timeline-label">${currentNode.label || ''}</span></div>
        <div class="card-footer">
          <span>${ev.ticker}</span>
          <span style="color:var(--primary);font-size:12px;font-weight:500">详情 →</span>
        </div>
      </div>`;
  },

  bindSearch() {
    const input = document.getElementById('discover-search');
    let timer;
    input.addEventListener('input', (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        this.feedSearch = e.target.value.trim();
        this.loadEvents();
      }, 300);
    });
  },

  bindFilters() {
    // 通用：点一次选中，再点一次取消（回到「全部」）
    const bindToggleGroup = (barId, btnClass, allValue, apply) => {
      const bar = document.getElementById(barId);
      if (!bar) return;
      bar.addEventListener('click', (e) => {
        const btn = e.target.closest('.' + btnClass);
        if (!btn) return;
        // 刷新 / 只看关注 有独立处理器，跳过
        if (btn.id === 'feed-refresh' || btn.id === 'feed-followed') return;

        const val = btn.dataset.filter !== undefined ? btn.dataset.filter
                  : btn.dataset.status !== undefined ? btn.dataset.status
                  : '';
        const wasActive = btn.classList.contains('active');

        // 仅清除本组的选项高亮；保留「只看关注」「刷新」等独立按钮的状态
        bar.querySelectorAll(`.${btnClass}:not(#feed-followed):not(#feed-refresh)`)
           .forEach(b => b.classList.remove('active'));

        if (wasActive && val !== allValue) {
          // 再点同一项 → 取消该条件，回到「全部」
          const allBtn = bar.querySelector(`.${btnClass}[data-filter="${allValue}"]`)
                      || bar.querySelector(`.${btnClass}[data-status="${allValue}"]`);
          if (allBtn) allBtn.classList.add('active');
          apply(allValue);
        } else {
          btn.classList.add('active');
          apply(val);
        }
        this.loadEvents();
      });
    };

    bindToggleGroup('discover-filters', 'filter-btn', '', (v) => { this.feedNature = v; });
    bindToggleGroup('status-filters', 'status-btn', '', (v) => { this.feedStatus = v; });
  },

  // 刷新：清除**全部**筛选条件（方向 / 状态 / 只看关注 / 搜索词）后重载
  async resetAllFilters() {
    this.feedNature = '';
    this.feedStatus = '';
    this.feedFollowed = false;
    this.feedSearch = '';

    const searchEl = document.getElementById('discover-search');
    if (searchEl) searchEl.value = '';

    // 方向：全部 高亮
    document.querySelectorAll('#discover-filters .filter-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('#discover-filters .filter-btn[data-filter=""]')?.classList.add('active');
    // 状态：全部状态 高亮
    document.querySelectorAll('#status-filters .status-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('#status-filters .status-btn[data-status=""]')?.classList.add('active');
    // 只看关注：取消
    document.getElementById('feed-followed')?.classList.remove('active');

    await this.loadEvents();
    this.toast('已重置全部筛选条件', '', 1700);
  },

  renderStatusCounts(counts) {
    document.querySelectorAll('.cnt[data-cnt]').forEach(el => {
      const n = counts[el.dataset.cnt] || 0;
      el.textContent = n > 0 ? n : '';
    });
  },

  bindRefresh() {
    // 刷新 = 重置全部条件 + 重载
    document.getElementById('feed-refresh')?.addEventListener('click', async (e) => {
      e.stopPropagation();
      const icon = e.currentTarget;
      icon.style.transform = 'rotate(360deg)';
      icon.style.transition = 'transform 0.6s';
      await this.resetAllFilters();
      setTimeout(() => { icon.style.transform = 'rotate(0deg)'; icon.style.transition = 'none'; }, 600);
    });
    // 只看关注
    document.getElementById('feed-followed')?.addEventListener('click', (e) => {
      const btn = e.currentTarget;
      this.feedFollowed = !this.feedFollowed;
      btn.classList.toggle('active', this.feedFollowed);
      if (this.feedFollowed && this.followedTickers.size === 0) {
        this.toast('还没有关注标的\n在「我的」添加持仓即可自动关注', 'warn', 3000);
      }
      this.loadEvents();
    });
    document.getElementById('fetch-new')?.addEventListener('click', () => this.fetchNewEvents());
    // 无限滚动：滚到底自动加载下一页
    const page = document.getElementById('tab-discover');
    if (page) {
      page.addEventListener('scroll', () => {
        if (page.scrollTop + page.clientHeight >= page.scrollHeight - 240) {
          this.maybeLoadMore();
        }
      }, { passive: true });
    }
  },

  // 触底处理：还有下一页就加载；已到底则提示可获取新事件
  async maybeLoadMore() {
    if (this._loadingMore || this._atEnd) return;
    if (this.events.length < this.feedTotal) {
      this._loadingMore = true;
      await this.loadEvents(true);
      this._loadingMore = false;
      if (this.events.length >= this.feedTotal) this.showFeedEnd();
    } else {
      this.showFeedEnd();
    }
  },

  showFeedEnd() {
    this._atEnd = true;
    const bar = document.getElementById('feed-end');
    if (bar) bar.style.display = 'block';
  },

  // 到底后：触发新一轮采集（新事件会增量进库）
  async fetchNewEvents() {
    const btn = document.getElementById('fetch-new');
    if (btn) { btn.disabled = true; btn.textContent = '正在抓取新事件…'; }
    try {
      await this.api('/api/pipeline/run', { method: 'POST', body: { days: 7 } });
      let tries = 0;
      const timer = setInterval(async () => {
        tries++;
        const d = await this.api('/api/events?limit=1').catch(() => null);
        if (d && d.total > this.feedTotal) {
          clearInterval(timer);
          this._atEnd = false;
          const endBar = document.getElementById('feed-end');
          if (endBar) endBar.style.display = 'none';
          await this.loadEvents();
          if (btn) { btn.disabled = false; btn.textContent = '获取新事件'; }
        } else if (tries > 30) {
          clearInterval(timer);
          if (btn) { btn.disabled = false; btn.textContent = '获取新事件'; }
        }
      }, 5000);
    } catch (e) {
      if (btn) { btn.disabled = false; btn.textContent = '获取新事件'; }
      alert('抓取失败：' + e.message);
    }
  },

  // ─── Event Detail ───
  async openEventDetail(eventId) {
    const ev = this.events.find(e => e.id === eventId);
    if (!ev) return;
    this.selectedEvent = ev;

    const [timeline, evidence, directions, versions] = await Promise.all([
      this.api(`/api/events/${eventId}/timeline`).catch(() => []),
      this.api(`/api/events/${eventId}/evidence`).catch(() => []),
      this.api(`/api/events/${eventId}/directions`).catch(() => []),
      this.api(`/api/events/${eventId}/versions`).catch(() => []),
    ]);

    const isSubscribed = this.subscriptions.includes(eventId);
    document.getElementById('modal-body').innerHTML =
      this.detailHTML(ev, timeline, evidence, directions, versions, isSubscribed);
    document.getElementById('event-modal').classList.add('active');
    // 右上角星号同步订阅状态
    this.updateBookmark(isSubscribed);

    document.querySelectorAll('.detail-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.detail-panel').forEach(p => p.style.display = 'none');
        document.getElementById(`panel-${tab.dataset.panel}`).style.display = 'block';
      });
    });
  },

  detailHTML(ev, timeline, evidence, directions, versions, isSubscribed) {
    // 同花顺惯例：红涨（利好）/ 绿跌（利空）
    const nbMap = {
      positive: { bg: 'var(--up-bg)', color: 'var(--up)', label: '利好' },
      negative: { bg: 'var(--down-bg)', color: 'var(--down)', label: '利空' },
      neutral: { bg: 'var(--flat-bg)', color: 'var(--flat)', label: '中性' },
      risk: { bg: 'var(--warn-bg)', color: 'var(--warn)', label: '风险' },
    };
    const nb = nbMap[ev.nature] || nbMap.neutral;

    const counts = { T0: 0, T1: 0, T2: 0, T3: 0 };
    evidence.forEach(e => counts[e.tier] = (counts[e.tier] || 0) + 1);
    const total = evidence.length || 1;

    const sourceAnnotation = `
      <div style="margin:10px 0;padding:8px 12px;background:#f0f9ff;border-radius:8px;font-size:11px;color:#0369a1">
        <strong>数据来源：</strong>iFinD/同花顺 MCP（公告+新闻语义检索）
        ｜ 抓取时间：${ev.crawl_time || '-'} ｜ 披露时间：${ev.disclosure_time || '-'} ｜ 事件时间：${ev.event_time || '-'}
      </div>`;

    const versionHTML = versions.length ? `
      <div style="margin:12px 0">
        <div style="font-size:12px;color:#6b7280;margin-bottom:6px">版本演化</div>
        ${versions.map((v, i) => {
          const cls = { update: 'v-update', deny: 'v-deny', correct: 'v-correct', expire: 'v-expire' }[v.change_type] || 'v-update';
          const label = { update: '更新', deny: '否认', correct: '更正', expire: '过期' }[v.change_type] || '更新';
          return `<div class="version-item ${i === 0 ? 'current' : ''}">
            <span class="version-type ${cls}">${label}</span>
            <span style="font-size:11px;color:#6b7280">v${v.version}</span>
            <div style="font-size:12px;margin-top:2px">${(v.headline || '').slice(0, 80)}</div>
            <div style="font-size:11px;color:#9ca3af">${v.status} · ${(v.created_at || '').slice(0, 10)}</div>
          </div>`;
        }).join('')}
      </div>` : '';

    const timelineHTML = timeline.length ? timeline.map(t => `
      <div class="timeline-item ${t.is_current ? 'current' : ''}">
        <div class="dot" style="background:${{ T0: '#10b981', T1: '#3b82f6', T2: '#f59e0b', T3: '#9ca3af' }[t.tier] || '#9ca3af'}"></div>
        <div class="content">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;flex-wrap:wrap">
            <strong style="font-size:13px">${t.label}</strong>
            <span style="font-size:11px;color:#6b7280">${t.date}</span>
            <span class="badge ${{ T0: 'badge-green', T1: 'badge-blue', T2: 'badge-orange', T3: 'badge-gray' }[t.tier]}">${t.tier}</span>
          </div>
          <div style="font-size:12px;color:#4b5563">${t.summary}</div>
        </div>
      </div>`).join('') : '<div style="color:#9ca3af;font-size:13px">暂无时间线数据</div>';

    const tierLabels = { T0: '官方披露(公告)', T1: '权威媒体', T2: '研报观点', T3: '市场传闻' };
    const tierColors = { T0: '#10b981', T1: '#3b82f6', T2: '#f59e0b', T3: '#9ca3af' };
    const byTier = { T0: [], T1: [], T2: [], T3: [] };
    evidence.forEach(e => { if (byTier[e.tier]) byTier[e.tier].push(e); });

    const evidenceHTML = Object.entries(byTier).map(([tier, items]) => !items.length ? '' : `
      <div style="margin-bottom:10px">
        <div style="font-size:12px;font-weight:600;color:${tierColors[tier]};margin-bottom:4px">${tierLabels[tier]} (${items.length})</div>
        ${items.map(item => `
          <div style="padding:8px;background:#f9fafb;border-radius:6px;margin-bottom:4px">
            <div style="display:flex;justify-content:space-between;font-size:12px">
              <strong>${item.source}</strong><span style="color:#9ca3af">${item.date}</span>
            </div>
            <div style="font-size:12px;color:#4b5563;margin-top:2px">${item.summary}</div>
          </div>`).join('')}
      </div>`).join('');

    const directionsHTML = directions.length ? directions.map(d => `
      <div class="dir-card">
        <div class="dir-header">
          <span class="dir-prob ${['高', '中高'].includes(d.probability) ? 'high' : 'mid'}">${d.probability}概率</span>
          <strong style="font-size:14px">${d.label}</strong>
        </div>
        <div style="font-size:12px;color:#4b5563;margin-bottom:6px">${d.description}</div>
        <div style="font-size:11px;color:#6b7280">依据: ${(d.supporting || []).join('、')}</div>
        <div style="font-size:11px;color:#6b7280">风险: ${d.risk}</div>
      </div>`).join('')
      : '<div style="color:#9ca3af;font-size:13px">暂无演化方向。可在「参谋」中提问，由 Agent 基于最新证据推演。</div>';

    return `
      <div style="background:${nb.bg};padding:16px;border-radius:12px;margin-bottom:16px">
        <div style="display:flex;gap:8px;margin-bottom:8px">
          <span class="badge" style="background:white;color:${nb.color}">${nb.label}</span>
          <span class="badge badge-gray">${ev.status}</span>
        </div>
        <h2 style="font-size:18px;margin-bottom:4px">${ev.ticker_name} · ${ev.theme}</h2>
        <p style="font-size:14px;color:#4b5563">${ev.headline}</p>
        <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;color:#9ca3af">
          <span>${ev.ticker}</span><span>更新 ${ev.updated_at}</span>
        </div>
      </div>
      ${sourceAnnotation}
      <div style="margin:12px 0">
        <div style="font-size:12px;color:#6b7280;margin-bottom:6px">证据权重</div>
        <div class="evidence-bar">
          <div class="evidence-segment e-t0" style="width:${(counts.T0 / total) * 100}%"></div>
          <div class="evidence-segment e-t1" style="width:${(counts.T1 / total) * 100}%"></div>
          <div class="evidence-segment e-t2" style="width:${(counts.T2 / total) * 100}%"></div>
          <div class="evidence-segment e-t3" style="width:${(counts.T3 / total) * 100}%"></div>
        </div>
        <div style="display:flex;gap:10px;margin-top:6px;font-size:11px">
          <span style="color:#10b981">● 公告 ${counts.T0}</span>
          <span style="color:#3b82f6">● 媒体 ${counts.T1}</span>
          <span style="color:#f59e0b">● 研报 ${counts.T2}</span>
          <span style="color:#9ca3af">● 传闻 ${counts.T3}</span>
        </div>
      </div>
      ${versionHTML}
      <div class="detail-tabs">
        <button class="detail-tab active" data-panel="timeline">事件脉络</button>
        <button class="detail-tab" data-panel="directions">其他说法</button>
      </div>
      <div id="panel-timeline" class="detail-panel">
        <div class="timeline-detail">${timelineHTML}</div>
        <div style="margin-top:16px">
          <div style="font-size:13px;font-weight:600;margin-bottom:8px">证据详情</div>
          ${evidenceHTML || '<div style="color:#9ca3af;font-size:13px">暂无证据</div>'}
        </div>
      </div>
      <div id="panel-directions" class="detail-panel" style="display:none">
        ${directionsHTML}
        ${ev.rumors?.length ? `
          <div style="margin-top:16px"><h4 style="font-size:14px;margin-bottom:8px">独立传闻区</h4>
          ${ev.rumors.map(r => `<div class="rumor-box">
            <div style="display:flex;gap:8px;margin-bottom:4px">
              <span class="rumor-tag">未证实</span>
              <span style="font-size:11px;color:#9ca3af">${r.source} · ${r.credibility}</span>
            </div>
            <div style="font-size:13px">${r.content}</div>
            <div style="font-size:11px;color:#9ca3af;margin-top:4px">${r.note}</div>
          </div>`).join('')}</div>` : ''}
      </div>
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
        <button id="detail-subscribe-btn" class="btn-primary" style="margin-bottom:8px" onclick="app.toggleSubscribe('${ev.id}')">
          ${isSubscribed ? '✓ 已订阅' : '☆ 订阅此事件'}
        </button>
        <p style="font-size:11px;color:#9ca3af;text-align:center">订阅后，该事件状态变化时将收到通知</p>
      </div>`;
  },

  closeModal() { document.getElementById('event-modal').classList.remove('active'); },

  // ─── Subscribe ───
  async loadSubscriptions() {
    try { this.subscriptions = await this.api('/api/subscriptions'); }
    catch { this.subscriptions = []; }
    await this.loadSubscribedEvents();
  },

  // 「我的」页：关注事件列表 + 计数
  async loadSubscribedEvents() {
    const list = document.getElementById('subscribed-list');
    if (!list) return;
    try {
      const d = await this.api('/api/subscriptions/events');
      const items = d.items || [];

      // 计数
      const ec = document.getElementById('sub-event-count');
      const tc = document.getElementById('sub-ticker-count');
      if (ec) ec.textContent = d.total || 0;
      if (tc) tc.textContent = d.ticker_count || 0;
      const hint = document.getElementById('subscribed-hint');
      if (hint) hint.textContent = items.length
        ? `共 ${items.length} 个 · 状态跃迁时通知你`
        : '订阅事件后，状态跃迁将通知你';

      if (!items.length) {
        list.innerHTML = '<div class="empty-state">暂无关注事件<br><span style="font-size:11px">在事件详情页点右上角 ☆ 即可订阅</span></div>';
        return;
      }

      const statusCls = {
        '官方确认': 'badge-st-confirmed', '媒体验证': 'badge-st-media',
        '未证实传闻': 'badge-st-rumor', '官方否认': 'badge-st-denied',
        '实质落地': 'badge-st-landed', '已过期': 'badge-st-expired',
      };
      list.innerHTML = items.map(ev => `
        <div class="sub-item" data-id="${ev.id}">
          <div class="sub-item-main" onclick="app.openSubscribed('${ev.id}')">
            <div class="sub-item-title">${ev.ticker_name} · ${ev.theme}</div>
            <div class="sub-item-meta">
              <span class="badge ${statusCls[ev.status] || 'badge-st-rumor'}">${ev.status}</span>
              <span class="badge ${ev.nature === 'positive' ? 'badge-up' : ev.nature === 'negative' ? 'badge-down' : 'badge-gray'}">${ev.nature_label}</span>
              <span class="sub-item-date">${ev.updated_at || ''}</span>
            </div>
          </div>
          <button class="sub-item-del" title="取消关注" onclick="event.stopPropagation();app.unsubFromProfile('${ev.id}')">★</button>
        </div>`).join('');
    } catch (e) {
      console.error('loadSubscribedEvents', e);
    }
  },

  // 「我的」页点击某关注事件 → 打开详情（先确保事件已加载）
  async openSubscribed(eventId) {
    let ev = this.events.find(e => e.id === eventId);
    if (!ev) {
      try {
        const d = await this.api(`/api/events/${encodeURIComponent(eventId)}`);
        if (d && d.id) { ev = d; this.events.unshift(ev); }
      } catch (e) { /* ignore */ }
    }
    if (ev) { this.selectedEvent = ev; await this.openEventDetail(eventId); }
  },

  // 「我的」页取消关注
  async unsubFromProfile(eventId) {
    await this.toggleSubscribe(eventId);
    await this.loadSubscribedEvents();
  },

  scrollToSubscribed() {
    document.getElementById('subscribed-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  // 右上角星号：未订阅 ☆ 灰，已订阅 ★ 黄
  updateBookmark(isSub) {
    const b = document.getElementById('detail-bookmark');
    if (!b) return;
    b.textContent = isSub ? '★' : '☆';
    b.classList.toggle('subscribed', !!isSub);
    b.title = isSub ? '已订阅，点击取消' : '订阅此事件';
  },

  // 点击右上角星号 → 切换订阅
  toggleBookmark() {
    if (!this.selectedEvent) return;
    this.toggleSubscribe(this.selectedEvent.id);
  },

  async toggleSubscribe(eventId) {
    const isSub = this.subscriptions.includes(eventId);
    try {
      if (isSub) {
        await this.api(`/api/subscriptions/${eventId}`, { method: 'DELETE' });
        this.subscriptions = this.subscriptions.filter(id => id !== eventId);
      } else {
        await this.api('/api/subscriptions', { method: 'POST', body: { event_id: eventId } });
        this.subscriptions.push(eventId);
      }
      const nowSub = this.subscriptions.includes(eventId);
      // 同步底部按钮
      const btn = document.getElementById('detail-subscribe-btn');
      if (btn) btn.textContent = nowSub ? '✓ 已订阅' : '☆ 订阅此事件';
      // 同步右上角星号
      if (this.selectedEvent && this.selectedEvent.id === eventId) this.updateBookmark(nowSub);
      // 同步「我的」页的关注列表与计数
      await this.loadSubscribedEvents();
    } catch (err) { alert('操作失败: ' + err.message); }
  },

  // ─── Chat (真实 Agent) ───
  bindChat() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');
    const send = () => {
      const text = input.value.trim();
      if (!text || this._chatBusy) return;
      this.addChatMsg('user', text);
      input.value = '';
      this.handleChat(text);
    };
    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  },

  addChatMsg(role, content, cards = null, citations = null) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;

    if (role === 'assistant') div.innerHTML = `<div class="bot-avatar">参谋</div>`;
    else div.innerHTML = `<div class="bot-avatar" style="background:#e5e7eb;color:#4b5563">我</div>`;

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    if (typeof content === 'string') {
      bubble.innerHTML = this._md(content);
    } else {
      bubble.appendChild(content);
    }
    div.appendChild(bubble);

    if (cards) {
      cards.forEach(ev => {
        const card = document.createElement('div');
        card.className = 'msg-card';
        card.innerHTML = `
          <div style="display:flex;gap:6px;margin-bottom:4px">
            <span class="badge ${ev.nature === 'positive' ? 'badge-green' : ev.nature === 'negative' ? 'badge-red' : 'badge-gray'}">${ev.nature_label}</span>
            <span style="font-size:11px;color:#9ca3af">${ev.status}</span>
          </div>
          <div style="font-size:13px;font-weight:600">${ev.ticker_name} · ${ev.theme}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:2px">${ev.headline}</div>`;
        card.addEventListener('click', () => this.openEventDetail(ev.id));
        bubble.appendChild(card);
      });
    }

    if (citations && citations.length) {
      const box = document.createElement('div');
      box.className = 'citation-box';
      box.innerHTML = `<div style="font-size:11px;font-weight:600;color:#0369a1;margin-bottom:6px">📎 数据来源（iFinD/同花顺 · 可追溯）</div>` +
        citations.slice(0, 6).map(c => `
          <div class="citation-item">
            <span class="badge ${c.tier === 'T0' ? 'badge-green' : c.tier === 'T1' ? 'badge-blue' : 'badge-gray'}" style="font-size:9px">${c.tier}</span>
            <div class="citation-body">
              <div class="citation-source">${(c.source || '').slice(0, 60)}</div>
              <div class="citation-summary">${(c.summary || '').slice(0, 100)}</div>
              <div class="citation-date">${c.date || ''} · ${c.data_source || 'iFinD'}</div>
            </div>
          </div>`).join('');
      bubble.appendChild(box);
    }

    container.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth' });
  },

  _md(text) {
    // 极简 markdown：加粗、标题、换行
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/^### (.*)$/gm, '<div style="font-weight:600;font-size:14px;margin:8px 0 4px">$1</div>')
      .replace(/^## (.*)$/gm, '<div style="font-weight:700;font-size:15px;margin:8px 0 4px">$1</div>')
      .replace(/^# (.*)$/gm, '<div style="font-weight:700;font-size:16px;margin:8px 0 4px">$1</div>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/^- (.*)$/gm, '<div style="padding-left:12px">• $1</div>')
      .replace(/\n/g, '<br>');
  },

  async handleChat(text) {
    this._chatBusy = true;
    document.getElementById('chat-send').disabled = true;

    const typing = document.createElement('div');
    typing.className = 'chat-msg';
    typing.id = 'typing-indicator';
    typing.innerHTML = `<div class="bot-avatar">参谋</div>
      <div class="msg-bubble">
        <div class="typing"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>
        <div style="font-size:11px;color:#9ca3af;margin-top:6px">正在调用 iFinD 检索真实数据...</div>
      </div>`;
    document.getElementById('chat-messages').appendChild(typing);
    typing.scrollIntoView({ behavior: 'smooth' });

    try {
      const res = await this.api('/api/chat', {
        method: 'POST',
        body: { message: text, history: this.chatHistory },
      });
      typing.remove();

      this.chatHistory.push({ role: 'user', content: text });
      this.chatHistory.push({ role: 'assistant', content: res.answer });

      this.addChatMsg('assistant', res.answer, null, res.citations);

      // 若引用了已采集到的事件，附带对应卡片
      const relatedCards = this._matchCards(res.citations);
      if (relatedCards.length) this.addChatMsg('assistant', '相关事件卡片：', relatedCards);

      if (res.tools_used && res.tools_used.length) {
        const meta = document.createElement('div');
        meta.style.cssText = 'font-size:10px;color:#9ca3af;text-align:center;margin:4px 0';
        meta.textContent = `已调用工具：${res.tools_used.map(t => t.tool).join('、')} · ${res.iterations} 轮推理`;
        document.getElementById('chat-messages').appendChild(meta);
      }
    } catch (err) {
      typing.remove();
      this.addChatMsg('assistant', '查询出错：' + err.message);
    } finally {
      this._chatBusy = false;
      document.getElementById('chat-send').disabled = false;
    }
  },

  _matchCards(citations) {
    if (!citations || !citations.length) return [];
    const matched = [];
    for (const ev of this.events) {
      if (citations.some(c => (c.source || '').includes(ev.ticker_name) || (c.summary || '').includes(ev.ticker_name))) {
        matched.push(ev);
      }
      if (matched.length >= 2) break;
    }
    return matched;
  },

  // ─── Holdings ───
  async loadHoldings() {
    try { this.holdings = await this.api('/api/holdings'); this.renderHoldings(); }
    catch (e) { console.error(e); }
  },

  renderHoldings() {
    const list = document.getElementById('holding-list');
    const badge = document.getElementById('holding-count');
    if (badge) badge.textContent = `持仓 ${this.holdings.length}`;
    if (!this.holdings.length) {
      list.innerHTML = '<div class="empty-state">暂无持仓<br><span style="font-size:11px">添加持仓可获取相关事件推送</span></div>';
      return;
    }
    list.innerHTML = this.holdings.map(h => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-size:14px;font-weight:500">${h.ticker_name}</div>
          <div style="font-size:12px;color:#9ca3af">${h.ticker}</div>
        </div>
        <button style="background:none;border:none;color:#d1d5db;cursor:pointer" onclick="app.deleteHolding(${h.id})">✕</button>
      </div>`).join('');
  },

  showAddHolding() { document.getElementById('holding-modal').classList.add('active'); },
  closeHoldingModal() { document.getElementById('holding-modal').classList.remove('active'); },

  async addHolding() {
    const ticker = document.getElementById('holding-ticker').value.trim();
    const name = document.getElementById('holding-name').value.trim();
    if (!ticker || !name) return this.toast('请填写股票代码和名称', 'warn');
    try {
      const r = await this.api('/api/holdings', {
        method: 'POST', body: { ticker, ticker_name: name },
      });
      this.closeHoldingModal();
      document.getElementById('holding-ticker').value = '';
      document.getElementById('holding-name').value = '';

      // 成功提示：持仓 + 关注标的 + 该标的事件数
      const n = r.event_count || 0;
      this.toast(
        `✓ 已添加持仓\n已关注「${r.ticker_name}」${n ? `，发现页有 ${n} 个该标的事件` : ''}`,
        'success', 3200);

      // 刷新持仓、关注列表、事件流（让「已关注」标记与计数同步）
      await Promise.all([this.loadHoldings(), this.loadSubscribedEvents(), this.loadTickers()]);
      await this.loadEvents();
    } catch (err) { this.toast('添加失败：' + err.message, 'error'); }
  },

  async deleteHolding(id) {
    try {
      await this.api(`/api/holdings/${id}`, { method: 'DELETE' });
      await this.loadHoldings();
      this.toast('已移除持仓', '', 1800);
    } catch (err) { this.toast('删除失败：' + err.message, 'error'); }
  },

  // 已关注标的列表（用于卡片角标与「只看关注」筛选）
  async loadTickers() {
    try {
      const d = await this.api('/api/tickers');
      this.followedTickers = new Set((d.items || []).map(x => x.ticker));
      const tc = document.getElementById('sub-ticker-count');
      if (tc) tc.textContent = d.total || 0;
    } catch { this.followedTickers = new Set(); }
  },

  // ─── Preferences ───
  async loadPreferences() {
    try { this.preferences = await this.api('/api/preferences'); this.updateProfileUI(); }
    catch (e) { console.error(e); }
  },

  updateProfileUI() {
    const map = { conservative: '保守型', moderate: '稳健型', aggressive: '激进型' };
    const el = document.getElementById('risk-level-display');
    if (el) el.textContent = map[this.preferences.risk_level] || '稳健型';
  },

  showSettings() { document.getElementById('settings-modal').classList.add('active'); },
  closeSettingsModal() { document.getElementById('settings-modal').classList.remove('active'); },

  async updateRiskLevel(level) {
    try {
      await this.api('/api/preferences', { method: 'POST', body: { risk_level: level } });
      this.preferences.risk_level = level;
      this.updateProfileUI();
      this.closeSettingsModal();
    } catch (err) { alert('更新失败: ' + err.message); }
  },

  // ─── Notifications ───
  async loadNotifications() {
    try {
      const data = await this.api('/api/notifications');
      this.notifications = data.list || [];
      const badge = document.getElementById('notif-badge');
      if (data.unread_count > 0) {
        badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
        badge.style.display = 'flex';
      } else badge.style.display = 'none';
    } catch (e) { console.error(e); }
  },

  showNotifications() {
    let modal = document.getElementById('notif-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'notif-modal';
      modal.className = 'modal';
      document.body.appendChild(modal);
    }
    modal.className = 'modal active';
    const typeLabel = {
      state_transition: '状态跃迁', evidence_update: '新证据', denial: '官方否认',
      correction: '更正', expiry: '已过期',
    };
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <button class="back-btn" onclick="app.closeNotifications()">←</button>
          <h3>通知中心</h3>
          <button class="notif-readall" onclick="app.markAllNotifRead()">全部已读</button>
        </div>
        <div class="modal-body" id="notif-list">
          ${this.notifications.length ? this.notifications.map(n => `
            <div class="notif-item ${n.read ? 'read' : 'unread'}" data-id="${n.id}" onclick="app.markNotifRead(${n.id})">
              <div style="display:flex;gap:8px;align-items:center;margin-bottom:5px">
                ${n.read ? '' : '<span class="notif-dot"></span>'}
                <span class="badge ${n.type === 'denial' ? 'badge-green' : n.type === 'expiry' ? 'badge-gray' : 'badge-blue'}">${typeLabel[n.type] || n.type}</span>
                <span style="font-size:11px;color:var(--text-3)">${(n.created_at || '').slice(0, 16)}</span>
                ${n.read ? '' : '<span class="notif-unread-tag">未读</span>'}
              </div>
              <div style="font-size:13.5px;font-weight:600;color:var(--text)">${n.title}</div>
              <div style="font-size:12px;color:var(--text-2);margin-top:3px">${n.content}</div>
              <div style="font-size:11px;color:var(--text-3);margin-top:5px">关联事件：${n.event_id}</div>
            </div>`).join('') : '<div class="empty-state">暂无通知<br><span style="font-size:11px">订阅事件或在「我的」添加持仓后，状态跃迁会通知你</span></div>'}
        </div>
      </div>`;
  },

  closeNotifications() { document.getElementById('notif-modal')?.classList.remove('active'); },

  async markAllNotifRead() {
    const btn = document.querySelector('.notif-readall');
    if (btn) { btn.disabled = true; btn.textContent = '处理中…'; }
    try {
      await this.api('/api/notifications/read-all', { method: 'POST' });
      await this.loadNotifications();     // 刷新铃铛徽标（清零）
      this.showNotifications();           // 重渲染列表（全部转为已读态）
      this.toast('✓ 已全部标为已读', 'success', 1800);
    } catch (e) {
      this.toast('操作失败：' + e.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = '全部已读'; }
    }
  },

  // 单条已读
  async markNotifRead(id) {
    const item = document.querySelector(`.notif-item[data-id="${id}"]`);
    if (item && item.classList.contains('read')) return;   // 已读则不重复请求
    try {
      await this.api(`/api/notifications/${id}/read`, { method: 'POST' });
      await this.loadNotifications();
      if (item) { item.classList.remove('unread'); item.classList.add('read'); }
    } catch (e) { console.error(e); }
  },

  // ─── Agent 运行状态 ───
  async loadAgentStatus() {
    const box = document.getElementById('agent-status');
    if (!box) return;
    try {
      const d = await this.api('/api/agents/status');
      const running = (a) => a.running ? '🟢 运行中' : '⚪ 空闲';
      const agents = Object.entries(d.agents).map(([name, a]) => `
        <div class="agent-row">
          <div class="agent-name">${name} <span class="agent-badge">${running(a)}</span></div>
          <div class="agent-model">模型：${a.model}</div>
          <div class="agent-role">${a.role}</div>
          <div class="agent-sched">调度：${a.schedule}</div>
        </div>`).join('');
      const data = d.data;
      box.innerHTML = `
        <div class="data-stat">
          事件 <b>${data.events}</b> · 证据 <b>${data.evidence}</b> · 版本 <b>${data.versions}</b>
          · 原始消息 <b>${data.raw_messages}</b>（待处理 ${data.pending_messages}）
          · 通知 <b>${data.notifications}</b>
        </div>
        ${agents}
        <div style="margin-top:10px;display:flex;gap:8px">
          <button class="btn-primary" style="flex:1;font-size:13px" onclick="app.runPipeline()">手动跑流水线</button>
          <button class="btn-primary" style="flex:1;font-size:13px;background:#f3f4f6;color:#374151" onclick="app.runReflect()">立即反思</button>
        </div>`;
    } catch (e) {
      box.innerHTML = `<div class="empty-state" style="padding:16px">加载失败：${e.message}</div>`;
    }
  },

  async runPipeline() {
    if (!confirm('将调用 iFinD 采集 + LLM 分析，耗时约 1-3 分钟，确认？')) return;
    try {
      const r = await this.api('/api/pipeline/run', { method: 'POST', body: { days: 30 } });
      alert(r.message || '已启动');
    } catch (e) { alert('启动失败：' + e.message); }
  },

  async runReflect() {
    try {
      const r = await this.api('/api/reflect/run', { method: 'POST' });
      alert(r.message || '已启动');
      setTimeout(() => this.loadAgentStatus(), 3000);
    } catch (e) { alert('启动失败：' + e.message); }
  },
};

document.addEventListener('DOMContentLoaded', () => app.init());
window.app = app;
