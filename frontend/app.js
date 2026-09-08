/* =========================================================================
   Data Drop — Frontend application
   Vanilla JS · no frameworks
   ========================================================================= */

(function () {
  'use strict';

  // ---------- State ----------
  const state = {
    sessionId: null,
    filename: null,
    profile: null,
    preview: null,
    suggestions: [],
    history: [],
    sortCol: null,
    sortDir: 1,
    activeChart: null,
    qualityReport: null,
    correlationReport: null,
    distributionReport: null,
    edaReport: null,
    aiInsights: null,
    activeView: 'home',
    datasets: [],
    activeDatasetIdx: 0,
    // Project management
    currentProject: null,
    projects: [],
  };

  const API = '';  // same origin
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);
  let dashboardAPI;

  // ---------- DOM refs ----------
  const dropZone = $('#dropZone');
  const fileInput = $('#fileInput');
  const uploadError = $('#uploadError');
  const loader = $('#loader');
  const loaderText = $('#loaderText');
  const toast = $('#toast');

  // =========================================================================
  // Init
  // =========================================================================
  function init() {
    // Theme
    initTheme();
    // Fetch upload limits from backend
    fetchUploadLimits();
    // Navigation
    bindNavigation();
    // Upload
    bindUpload();
    // Existing bindings
    bindSidebar();
    bindClean();
    bindDownloads();
    bindChartControls();
    bindShare();
    bindEdaReport();
    bindAiInsights();
    bindAskData();
    bindFeatureEngineering();
    bindStats();
    bindTools();
    dashboardAPI = bindDashboard();
    // New features
    bindGlobalSearch();
    bindFloatingAI();
    // Project management
    bindCreateProject();
    loadProjects();
    // Workspace
    loadWorkspace();
    // Restore session from URL hash.
    const hash = window.location.hash;
    const match = hash.match(/session=([a-f0-9]+)/i);
    if (match) {
      loadSession(match[1]);
    }
  }

  // =========================================================================
  // Theme persistence
  // =========================================================================
  function initTheme() {
    const saved = localStorage.getItem('dd-theme');
    if (saved) {
      document.documentElement.setAttribute('data-theme', saved);
      updateThemeIcons(saved);
    }
    $('#themeToggle')?.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('dd-theme', next);
      updateThemeIcons(next);
    });
  }

  function updateThemeIcons(theme) {
    const dark = $('#themeIconDark');
    const light = $('#themeIconLight');
    if (dark && light) {
      dark.hidden = theme === 'light';
      light.hidden = theme === 'dark';
    }
  }

  // =========================================================================
  // Navigation
  // =========================================================================
  function bindNavigation() {
    // Sidebar toggle
    $('#sidebarToggle')?.addEventListener('click', () => {
      const nav = $('#navSidebar');
      nav.classList.toggle('collapsed');
      localStorage.setItem('dd-nav-collapsed', nav.classList.contains('collapsed'));
    });
    // Restore nav state
    if (localStorage.getItem('dd-nav-collapsed') === 'true') {
      $('#navSidebar')?.classList.add('collapsed');
    }

    // Nav items
    $$('.nav-item').forEach((item) => {
      item.addEventListener('click', () => {
        const view = item.dataset.view;
        if (!view) return;
        // Check if session required
        if (item.hasAttribute('data-requires-session') && !state.sessionId) {
          showToast('Upload a dataset first', 'info');
          return;
        }
        navigateTo(view);
      });
    });
  }

  function navigateTo(viewName) {
    // Update nav active state
    $$('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.view === viewName));
    // Switch views
    $$('.view').forEach((v) => v.classList.remove('active'));
    const target = $(`#view-${viewName}`);
    if (target) target.classList.add('active');
    state.activeView = viewName;
    // Lazy load content
    lazyLoadView(viewName);
    // Close mobile nav
    if (window.innerWidth <= 980) {
      $('#navSidebar')?.classList.add('collapsed');
    }
  }

  function lazyLoadView(viewName) {
    if (!state.sessionId) return;
    switch (viewName) {
      case 'report':
        if (!state.qualityReport) loadQualityReport();
        break;
      case 'correlation':
        if (!state.correlationReport) loadCorrelationReport();
        break;
      case 'distribution':
        if (!state.distributionReport) loadDistributionReport();
        break;
      case 'dashboard':
        if (dashboardAPI) dashboardAPI.loadSavedList();
        break;
      case 'charts':
        setTimeout(() => {
          const plot = document.querySelector('#chartContainer .js-plotly-plot');
          if (plot) Plotly.Plots.resize(plot);
        }, 100);
        break;
      case 'projects':
        loadProjects();
        break;
    }
  }

  // =========================================================================
  // Workspace management
  // =========================================================================
  function loadWorkspace() {
    try {
      const saved = localStorage.getItem('dd-workspace');
      if (saved) {
        state.datasets = JSON.parse(saved);
      }
    } catch (e) { /* ignore */ }
    renderWorkspace();
    renderHomeStats();
  }

  function saveWorkspace() {
    try {
      localStorage.setItem('dd-workspace', JSON.stringify(state.datasets));
    } catch (e) { /* ignore */ }
  }

  function addDatasetToWorkspace(data) {
    const ds = {
      id: data.session_id,
      name: data.filename,
      rows: data.profile.n_rows,
      cols: data.profile.n_cols,
      memory: data.profile.memory_kb,
      addedAt: Date.now(),
    };
    // Avoid duplicates
    if (!state.datasets.find((d) => d.id === ds.id)) {
      state.datasets.unshift(ds);
      saveWorkspace();
      renderWorkspace();
      renderHomeStats();
    }
  }

  function renderWorkspace() {
    const container = $('#wsDatasets');
    if (!container) return;
    if (!state.datasets.length) {
      container.innerHTML = `<div class="workspace-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".3"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
        <p>No datasets yet. Upload a file to get started.</p>
      </div>`;
      return;
    }
    container.innerHTML = state.datasets.map((ds) => `
      <div class="ws-dataset-card" data-id="${ds.id}">
        <div class="ws-ds-header">
          <div class="ws-ds-name" title="${esc(ds.name)}">${esc(ds.name)}</div>
          <span class="ws-ds-badge">Active</span>
        </div>
        <div class="ws-ds-stats">
          <div class="ws-ds-stat"><span>Rows</span><span>${ds.rows?.toLocaleString() || '—'}</span></div>
          <div class="ws-ds-stat"><span>Columns</span><span>${ds.cols || '—'}</span></div>
          <div class="ws-ds-stat"><span>Memory</span><span>${ds.memory || '—'} KB</span></div>
          <div class="ws-ds-stat"><span>Added</span><span>${new Date(ds.addedAt).toLocaleDateString()}</span></div>
        </div>
        <div class="ws-ds-actions">
          <button class="btn btn-primary btn-sm ws-analyze" data-id="${ds.id}">Analyze</button>
          <button class="btn btn-ghost btn-sm ws-remove" data-id="${ds.id}">Remove</button>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.ws-analyze').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        loadSession(btn.dataset.id);
        navigateTo('preview');
      });
    });
    container.querySelectorAll('.ws-remove').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        state.datasets = state.datasets.filter((d) => d.id !== btn.dataset.id);
        saveWorkspace();
        renderWorkspace();
        renderHomeStats();
        showToast('Dataset removed from workspace', 'info');
      });
    });
  }

  function renderHomeStats() {
    const stats = $('#homeStats');
    if (!stats) return;
    if (state.datasets.length > 0 || state.sessionId) {
      stats.hidden = false;
      $('#homeDatasetsCount').textContent = state.datasets.length;
      // Load dashboard count from localStorage
      try {
        const saved = localStorage.getItem('dd-dashboards');
        const dashboards = saved ? JSON.parse(saved) : [];
        $('#homeDashboardsCount').textContent = dashboards.length || 0;
      } catch (e) {
        $('#homeDashboardsCount').textContent = '0';
      }
      const recentSection = $('#homeRecentSection');
      if (recentSection && state.datasets.length > 0) {
        recentSection.hidden = false;
        renderRecentActivity();
      }
    }
  }

  function renderRecentActivity() {
    const grid = $('#homeRecentGrid');
    if (!grid) return;
    grid.innerHTML = state.datasets.slice(0, 6).map((ds) => `
      <div class="home-recent-card" data-id="${ds.id}">
        <div class="home-recent-icon" style="background:rgba(124,156,255,.12);color:var(--accent)">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
        </div>
        <div class="home-recent-info">
          <div class="home-recent-name">${esc(ds.name)}</div>
          <div class="home-recent-meta">${ds.rows?.toLocaleString() || '—'} rows · ${ds.cols || '—'} cols</div>
        </div>
      </div>
    `).join('');

    grid.querySelectorAll('.home-recent-card').forEach((card) => {
      card.addEventListener('click', () => {
        loadSession(card.dataset.id);
        navigateTo('preview');
      });
    });
  }

  // =========================================================================
  // Project management
  // =========================================================================
  async function loadProjects() {
    try {
      const res = await fetch(`${API}/api/projects`);
      if (res.ok) {
        state.projects = await res.json();
        renderProjectsList();
      }
    } catch (e) { /* ignore */ }
  }

  async function createProject(name, description = '') {
    try {
      const res = await fetch(`${API}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description }),
      });
      if (res.ok) {
        const project = await res.json();
        state.projects.unshift(project);
        renderProjectsList();
        showToast(`Project "${name}" created`, 'success');
        return project;
      }
    } catch (e) {
      showToast('Failed to create project', 'error');
    }
    return null;
  }

  async function openProject(projectId) {
    try {
      const res = await fetch(`${API}/api/projects/${projectId}`);
      if (res.ok) {
        state.currentProject = await res.json();
        renderProjectHome();
        navigateTo('project-home');
      }
    } catch (e) {
      showToast('Failed to load project', 'error');
    }
  }

  async function deleteProject(projectId) {
    try {
      const res = await fetch(`${API}/api/projects/${projectId}`, { method: 'DELETE' });
      if (res.ok) {
        state.projects = state.projects.filter(p => p.id !== projectId);
        if (state.currentProject?.id === projectId) {
          state.currentProject = null;
        }
        renderProjectsList();
        showToast('Project deleted', 'success');
      }
    } catch (e) {
      showToast('Failed to delete project', 'error');
    }
  }

  async function addDatasetToProject(projectId, sessionId, filename) {
    try {
      const res = await fetch(`${API}/api/projects/${projectId}/datasets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, filename }),
      });
      if (res.ok) {
        const project = await res.json();
        state.currentProject = project;
        renderProjectHome();
        showToast('Dataset added to project', 'success');
      }
    } catch (e) {
      showToast('Failed to add dataset', 'error');
    }
  }

  async function removeDatasetFromProject(projectId, sessionId) {
    try {
      const res = await fetch(`${API}/api/projects/${projectId}/datasets/${sessionId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        const project = await res.json();
        state.currentProject = project;
        renderProjectHome();
        showToast('Dataset removed from project', 'success');
      }
    } catch (e) {
      showToast('Failed to remove dataset', 'error');
    }
  }

  function renderProjectsList() {
    const container = $('#projectsList');
    if (!container) return;
    if (!state.projects.length) {
      container.innerHTML = `<div class="projects-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".3"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        <p>No projects yet. Create your first project to organize datasets and dashboards.</p>
      </div>`;
      return;
    }
    container.innerHTML = state.projects.map(p => `
      <div class="project-card" data-id="${p.id}">
        <div class="project-card-header">
          <div class="project-card-icon" style="background:rgba(124,156,255,.15);color:var(--accent)">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
          </div>
          <div class="project-card-info">
            <div class="project-card-name">${esc(p.name)}</div>
            <div class="project-card-desc">${esc(p.description || 'No description')}</div>
          </div>
        </div>
        <div class="project-card-stats">
          <span>${p.dataset_count || 0} datasets</span>
          <span>${p.dashboard_count || 0} dashboards</span>
          <span>${new Date(p.updated_at).toLocaleDateString()}</span>
        </div>
        <div class="project-card-actions">
          <button class="btn btn-primary btn-sm project-open" data-id="${p.id}">Open</button>
          <button class="btn btn-ghost btn-sm project-delete" data-id="${p.id}">Delete</button>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.project-open').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openProject(btn.dataset.id);
      });
    });
    container.querySelectorAll('.project-delete').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm('Delete this project?')) {
          deleteProject(btn.dataset.id);
        }
      });
    });
  }

  function renderProjectHome() {
    const container = $('#projectHomeContent');
    if (!container || !state.currentProject) return;
    const p = state.currentProject;
    container.innerHTML = `
      <div class="project-home-header">
        <h2>${esc(p.name)}</h2>
        <p class="project-home-desc">${esc(p.description || 'No description')}</p>
        <div class="project-home-meta">
          <span>Created ${new Date(p.created_at).toLocaleDateString()}</span>
          <span>${p.datasets?.length || 0} datasets</span>
          <span>${p.dashboards?.length || 0} dashboards</span>
        </div>
      </div>
      <div class="project-home-section">
        <h3>Datasets</h3>
        <div class="project-datasets-list" id="projectDatasetsList">
          ${(p.datasets || []).map(d => `
            <div class="project-dataset-item">
              <span>${esc(d.filename)}</span>
              <button class="btn btn-ghost btn-sm project-remove-ds" data-sid="${d.session_id}">Remove</button>
            </div>
          `).join('') || '<p class="project-empty-text">No datasets added yet.</p>'}
        </div>
      </div>
      <div class="project-home-section">
        <h3>Activity</h3>
        <div class="project-activity-list">
          ${(p.activity_log || []).slice(0, 10).map(a => `
            <div class="project-activity-item">
              <span class="project-activity-action">${esc(a.action)}</span>
              <span class="project-activity-details">${esc(a.details)}</span>
              <span class="project-activity-time">${new Date(a.timestamp).toLocaleString()}</span>
            </div>
          `).join('') || '<p class="project-empty-text">No activity yet.</p>'}
        </div>
      </div>
    `;

    container.querySelectorAll('.project-remove-ds').forEach(btn => {
      btn.addEventListener('click', () => {
        if (state.currentProject) {
          removeDatasetFromProject(state.currentProject.id, btn.dataset.sid);
        }
      });
    });
  }

  function bindCreateProject() {
    const btn = $('#createProjectBtn');
    const modal = $('#createProjectModal');
    const form = $('#createProjectForm');
    const closeBtn = modal?.querySelector('.modal-close');

    btn?.addEventListener('click', () => {
      modal.hidden = false;
    });
    closeBtn?.addEventListener('click', () => {
      modal.hidden = true;
    });
    modal?.addEventListener('click', (e) => {
      if (e.target === modal) modal.hidden = true;
    });

    form?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = form.querySelector('#projectName')?.value.trim();
      const desc = form.querySelector('#projectDesc')?.value.trim();
      if (!name) return;
      const project = await createProject(name, desc);
      if (project) {
        modal.hidden = true;
        form.reset();
        openProject(project.id);
      }
    });
  }

  // =========================================================================
  // Global Search
  // =========================================================================
  function bindGlobalSearch() {
    const btn = $('#globalSearchBtn');
    const modal = $('#searchModal');
    const input = $('#searchModalInput');
    const close = () => { modal.hidden = true; };

    btn?.addEventListener('click', () => {
      modal.hidden = false;
      setTimeout(() => input?.focus(), 50);
      renderSearchResults('');
    });

    modal?.addEventListener('click', (e) => {
      if (e.target === modal) close();
    });

    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        modal.hidden = false;
        setTimeout(() => input?.focus(), 50);
        renderSearchResults('');
      }
      if (e.key === 'Escape' && !modal?.hidden) {
        close();
      }
    });

    input?.addEventListener('input', () => {
      renderSearchResults(input.value);
    });
  }

  function renderSearchResults(query) {
    const container = $('#searchResults');
    if (!container) return;

    const results = [];
    const q = query.toLowerCase().trim();

    // Search navigation items
    const navItems = [
      { name: 'Home', view: 'home', type: 'Navigation', icon: '🏠' },
      { name: 'Workspace', view: 'workspace', type: 'Navigation', icon: '📁' },
      { name: 'Datasets', view: 'datasets', type: 'Navigation', icon: '🗄️' },
      { name: 'Merge Center', view: 'merge', type: 'Navigation', icon: '🔗' },
      { name: 'Data Preview', view: 'preview', type: 'Analysis', icon: '📊' },
      { name: 'Charts', view: 'charts', type: 'Analysis', icon: '📈' },
      { name: 'Cleaning', view: 'clean', type: 'Analysis', icon: '🧹' },
      { name: 'Quality Report', view: 'report', type: 'Analysis', icon: '📋' },
      { name: 'Correlation', view: 'correlation', type: 'Analysis', icon: '🔗' },
      { name: 'Distribution', view: 'distribution', type: 'Analysis', icon: '📉' },
      { name: 'Statistics', view: 'stats', type: 'Analysis', icon: '🧮' },
      { name: 'AI Insights', view: 'ai-insights', type: 'AI', icon: '🤖' },
      { name: 'Ask Data', view: 'ask-data', type: 'AI', icon: '💬' },
      { name: 'Feature Engineering', view: 'features', type: 'Tools', icon: '⚙️' },
      { name: 'Tools', view: 'tools', type: 'Tools', icon: '🔧' },
      { name: 'Dashboard', view: 'dashboard', type: 'Output', icon: '📊' },
      { name: 'EDA Report', view: 'eda-report', type: 'Output', icon: '📄' },
    ];

    navItems.forEach((item) => {
      if (!q || item.name.toLowerCase().includes(q) || item.type.toLowerCase().includes(q)) {
        results.push(item);
      }
    });

    // Search datasets
    state.datasets.forEach((ds) => {
      if (!q || ds.name.toLowerCase().includes(q)) {
        results.push({ name: ds.name, view: 'preview', type: 'Dataset', icon: '🗄️', id: ds.id });
      }
    });

    // Search columns
    if (state.profile?.columns) {
      state.profile.columns.forEach((col) => {
        if (!q || col.name.toLowerCase().includes(q)) {
          results.push({ name: col.name, view: 'preview', type: `Column (${col.type})`, icon: '📐' });
        }
      });
    }

    if (!results.length) {
      container.innerHTML = '<div class="search-empty">No results found</div>';
      return;
    }

    container.innerHTML = results.slice(0, 12).map((r) => `
      <div class="search-result-item" data-view="${r.view}" data-id="${r.id || ''}">
        <div class="search-result-icon" style="background:var(--bg-elev2);font-size:16px">${r.icon}</div>
        <div class="search-result-info">
          <div class="search-result-name">${esc(r.name)}</div>
          <div class="search-result-type">${esc(r.type)}</div>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.search-result-item').forEach((item) => {
      item.addEventListener('click', () => {
        const view = item.dataset.view;
        const id = item.dataset.id;
        if (id) {
          loadSession(id);
        }
        navigateTo(view);
        $('#searchModal').hidden = true;
      });
    });
  }

  // =========================================================================
  // Floating AI Assistant
  // =========================================================================
  function bindFloatingAI() {
    const fab = $('#aiFab');
    const panel = $('#aiAssistantPanel');
    const close = $('#aiAssistantClose');
    const input = $('#aiAssistantInput');
    const send = $('#aiAssistantSend');
    const body = $('#aiAssistantBody');

    fab?.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) setTimeout(() => input?.focus(), 50);
    });

    close?.addEventListener('click', () => {
      panel.hidden = true;
    });

    const sendQuestion = async () => {
      const q = input?.value?.trim();
      if (!q || !state.sessionId) {
        if (!state.sessionId) showToast('Upload a dataset first', 'info');
        return;
      }
      input.value = '';
      // Add user message
      const userMsg = document.createElement('div');
      userMsg.className = 'ai-assistant-msg user';
      userMsg.textContent = q;
      body.appendChild(userMsg);

      // Add loading
      const loadingMsg = document.createElement('div');
      loadingMsg.className = 'ai-assistant-msg assistant';
      loadingMsg.innerHTML = '<div class="loader-spinner" style="width:20px;height:20px;border-width:2px"></div>';
      body.appendChild(loadingMsg);
      body.scrollTop = body.scrollHeight;

      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/ask`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q }),
        });
        const data = await res.json();
        loadingMsg.remove();
        const assistantMsg = document.createElement('div');
        assistantMsg.className = 'ai-assistant-msg assistant';
        if (data.error) {
          assistantMsg.textContent = data.error;
        } else if (data.answer != null) {
          assistantMsg.textContent = String(data.answer);
        } else if (data.result_text) {
          assistantMsg.textContent = data.result_text;
        } else {
          assistantMsg.textContent = 'I processed your question. Check the Ask Data tab for full results.';
        }
        body.appendChild(assistantMsg);
        body.scrollTop = body.scrollHeight;
      } catch (e) {
        loadingMsg.remove();
        const errMsg = document.createElement('div');
        errMsg.className = 'ai-assistant-msg assistant';
        errMsg.textContent = 'Sorry, I could not process that question.';
        body.appendChild(errMsg);
      }
    };

    send?.addEventListener('click', sendQuestion);
    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendQuestion();
    });

    // Suggestion buttons
    $$('.ai-assist-sug').forEach((btn) => {
      btn.addEventListener('click', () => {
        input.value = btn.dataset.q;
        sendQuestion();
      });
    });
  }

  // =========================================================================
  // Upload & drag-drop
  // =========================================================================
  function bindUpload() {
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) handleFile(e.target.files[0]);
    });

    ['dragenter', 'dragover'].forEach((evt) =>
      dropZone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('dragover');
      })
    );
    ['dragleave', 'drop'].forEach((evt) =>
      dropZone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (evt === 'dragleave' && e.currentTarget.contains(e.relatedTarget)) return;
        dropZone.classList.remove('dragover');
      })
    );
    dropZone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files.length) handleFile(files[0]);
    });

    // Allow dropping anywhere on the page.
    ['dragover', 'drop'].forEach((evt) =>
      document.addEventListener(evt, (e) => {
        e.preventDefault();
      })
    );

    $('#newFileBtn')?.addEventListener('click', () => {
      navigateTo('home');
      fileInput.value = '';
    });
    $('#wsUploadBtn')?.addEventListener('click', () => fileInput.click());
  }

  let uploadLimits = null;

  async function fetchUploadLimits() {
    try {
      const res = await fetch(`${API}/api/upload/limits`);
      if (res.ok) uploadLimits = await res.json();
    } catch (e) { /* ignore */ }
  }

  function validateFile(file) {
    const validExts = ['.csv', '.json', '.tsv', '.txt', '.xlsx', '.parquet'];
    const name = file.name.toLowerCase();
    const ok = validExts.some((ext) => name.endsWith(ext));
    if (!ok) return 'Unsupported file type. Please use CSV, JSON, TSV, XLSX, or Parquet.';
    return null;
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  async function computeFileHash(file) {
    const buf = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buf);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }

  async function handleFile(file) {
    uploadError.hidden = true;
    const err = validateFile(file);
    if (err) { showUploadError(err); return; }

    const CHUNKED_THRESHOLD = 5 * 1024 * 1024; // 5 MB
    if (file.size > CHUNKED_THRESHOLD) {
      await handleChunkedUpload(file);
    } else {
      await handleLegacyUpload(file);
    }
  }

  async function handleLegacyUpload(file) {
    showLoader('Uploading & analyzing…');
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API}/api/upload`, { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');
      onSessionLoaded(data);
    } catch (e) {
      showUploadError(e.message || 'Could not process file.');
    } finally {
      hideLoader();
    }
  }

  async function handleChunkedUpload(file) {
    const chunkSize = uploadLimits?.chunk_size || 5 * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / chunkSize);
    const fileHash = await computeFileHash(file);

    showLoader(`Uploading ${formatBytes(file.size)} in ${totalChunks} chunks…`);
    updateUploadProgress(0, totalChunks, file.name, file.size);

    try {
      const initRes = await fetch(`${API}/api/upload/chunked/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: file.name,
          file_size: file.size,
          total_chunks: totalChunks,
          file_hash: fileHash,
        }),
      });
      const initData = await initRes.json();
      if (!initRes.ok) throw new Error(initData.detail || 'Failed to initialize upload');

      const uploadId = initData.upload_id;

      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        const chunk = file.slice(start, end);
        const fd = new FormData();
        fd.append('file', chunk, file.name);

        const chunkRes = await fetch(`${API}/api/upload/chunked/${uploadId}/chunk/${i}?total_chunks=${totalChunks}`, {
          method: 'POST',
          body: fd,
        });
        const chunkData = await chunkRes.json();
        if (!chunkRes.ok) throw new Error(chunkData.detail || `Chunk ${i} failed`);

        updateUploadProgress(i + 1, totalChunks, file.name, file.size);
      }

      showLoader('Assembling and processing file…');
      const completeRes = await fetch(`${API}/api/upload/chunked/${uploadId}/complete`, {
        method: 'POST',
      });
      const completeData = await completeRes.json();
      if (!completeRes.ok) throw new Error(completeData.detail || 'Assembly failed');

      if (completeData.processing_mode === 'background') {
        showLoader('Processing in background…');
        await pollBackgroundProcessing(completeData.session_id, uploadId);
      } else {
        onSessionLoaded(completeData);
      }
    } catch (e) {
      showUploadError(e.message || 'Chunked upload failed.');
    } finally {
      hideLoader();
      hideUploadProgress();
    }
  }

  async function pollBackgroundProcessing(sessionId, uploadId) {
    const maxAttempts = 300;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const res = await fetch(`${API}/api/session/${sessionId}`);
        const data = await res.json();
        if (res.ok && data.profile) {
          onSessionLoaded(data);
          return;
        }
        if (data.processing) {
          showLoader(`Processing… (attempt ${attempt + 1})`);
          continue;
        }
      } catch (e) { /* retry */ }
    }
    showUploadError('Background processing timed out. Try refreshing.');
  }

  function updateUploadProgress(chunksDone, totalChunks, filename, fileSize) {
    const pct = totalChunks > 0 ? Math.round((chunksDone / totalChunks) * 100) : 0;
    const existing = document.getElementById('uploadProgressBar');
    if (existing) {
      const pctEl = existing.querySelector('.upload-progress-pct');
      const labelEl = existing.querySelector('.upload-progress-label');
      const fillEl = existing.querySelector('.upload-progress-fill');
      if (pctEl) pctEl.textContent = pct + '%';
      if (labelEl) labelEl.textContent = `${chunksDone}/${totalChunks} chunks — ${formatBytes(fileSize)}`;
      if (fillEl) fillEl.style.width = pct + '%';
    } else {
      const bar = document.createElement('div');
      bar.id = 'uploadProgressBar';
      bar.className = 'upload-progress-bar';
      bar.innerHTML = `
        <div class="upload-progress-header">
          <span class="upload-progress-label">${chunksDone}/${totalChunks} chunks — ${formatBytes(fileSize)}</span>
          <span class="upload-progress-pct">${pct}%</span>
        </div>
        <div class="upload-progress-track"><div class="upload-progress-fill" style="width:${pct}%"></div></div>
      `;
      const errEl = $('#uploadError');
      if (errEl) errEl.parentNode.insertBefore(bar, errEl.nextSibling);
    }
  }

  function hideUploadProgress() {
    const bar = document.getElementById('uploadProgressBar');
    if (bar) bar.remove();
  }

  function showUploadError(msg) {
    uploadError.textContent = msg;
    uploadError.hidden = false;
  }

  // =========================================================================
  // Session loading (upload or URL hash)
  // =========================================================================
  async function loadSession(sessionId) {
    showLoader('Loading session…');
    try {
      const res = await fetch(`${API}/api/session/${sessionId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Session not found');
      onSessionLoaded(data);
    } catch (e) {
      showToast('Could not load shared session: ' + e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  function onSessionLoaded(data) {
    state.sessionId = data.session_id;
    state.filename = data.filename;
    state.profile = data.profile;
    state.preview = data.preview;
    state.suggestions = data.suggestions || [];
    state.history = data.history || [];
    state.sortCol = null;
    state.qualityReport = null;
    state.correlationReport = null;
    state.distributionReport = null;

    // Update URL hash for sharing.
    window.location.hash = `session=${state.sessionId}`;

    // Show topbar buttons
    $('#shareBtn').hidden = false;
    $('#newFileBtn').hidden = false;

    // Add to workspace
    addDatasetToWorkspace(data);

    // Render everything.
    $('#filenameLabel').textContent = state.filename;
    renderProfile();
    renderPreview();
    renderChartSuggestions();
    populateChartSelectors();
    renderHistory();
    populateFeatureSelects();

    // Auto-render the top suggestion.
    if (state.suggestions.length) {
      selectSuggestion(state.suggestions[0]);
    }

    showToast(`Loaded ${state.profile.n_rows.toLocaleString()} rows × ${state.profile.n_cols} columns`, 'success');
    
    // Navigate to preview
    navigateTo('preview');
  }

  function resetToUpload() {
    window.location.hash = '';
    navigateTo('home');
    fileInput.value = '';
    state.qualityReport = null;
    state.correlationReport = null;
    state.distributionReport = null;
  }

  // =========================================================================
  // Profile panel
  // =========================================================================
  function renderProfile() {
    const p = state.profile;
    const summary = $('#profileSummary');
    const nullPct = p.n_rows ? (p.total_nulls / (p.n_rows * p.n_cols) * 100) : 0;

    summary.innerHTML = `
      <div class="stat-card"><div class="stat-val">${p.n_rows.toLocaleString()}</div><div class="stat-label">Rows</div></div>
      <div class="stat-card"><div class="stat-val">${p.n_cols}</div><div class="stat-label">Columns</div></div>
      <div class="stat-card"><div class="stat-val ${p.total_nulls ? 'warn' : 'good'}">${p.total_nulls.toLocaleString()}</div><div class="stat-label">Null Cells</div></div>
      <div class="stat-card"><div class="stat-val ${p.duplicate_rows ? 'warn' : 'good'}">${p.duplicate_rows.toLocaleString()}</div><div class="stat-label">Duplicates</div></div>
      <div class="stat-card wide"><div class="stat-val">${nullPct.toFixed(1)}%</div><div class="stat-label">Null Density · ${p.memory_kb} KB memory</div></div>
    `;

    // Column cards grouped by type.
    const typeOrder = ['numeric', 'datetime', 'categorical'];
    const grouped = {};
    p.columns.forEach((c) => {
      (grouped[c.type] = grouped[c.type] || []).push(c);
    });

    let html = '';
    typeOrder.forEach((type) => {
      if (!grouped[type]) return;
      html += `<div class="profile-section-title">${type} (${grouped[type].length})</div>`;
      grouped[type].forEach((c, i) => {
        html += renderColCard(c, i);
      });
    });
    $('#profileColumns').innerHTML = html;
  }

  function renderColCard(c, idx) {
    let extra = '';
    if (c.type === 'numeric') {
      extra = `
        <div class="col-stats">
          <div class="col-stat"><span class="k">min</span><span class="v">${fmt(c.min)}</span></div>
          <div class="col-stat"><span class="k">max</span><span class="v">${fmt(c.max)}</span></div>
          <div class="col-stat"><span class="k">mean</span><span class="v">${fmt(c.mean)}</span></div>
          <div class="col-stat"><span class="k">median</span><span class="v">${fmt(c.median)}</span></div>
          <div class="col-stat"><span class="k">std</span><span class="v">${fmt(c.std)}</span></div>
          <div class="col-stat"><span class="k">unique</span><span class="v">${c.unique_count}</span></div>
        </div>`;
    } else if (c.type === 'datetime') {
      extra = `
        <div class="col-stats">
          <div class="col-stat"><span class="k">min</span><span class="v">${fmt(c.min)}</span></div>
          <div class="col-stat"><span class="k">max</span><span class="v">${fmt(c.max)}</span></div>
          <div class="col-stat"><span class="k">unique</span><span class="v">${c.unique_count}</span></div>
        </div>`;
    } else {
      if (c.top_values && c.top_values.length) {
        extra = `<div class="top-values">` +
          c.top_values.slice(0, 5).map((t) =>
            `<div class="top-value-row"><span class="tv-val">${esc(t.value)}</span><span class="tv-count">${t.count}</span></div>`
          ).join('') + `</div>`;
      }
      extra += `<div class="col-stats"><div class="col-stat"><span class="k">unique</span><span class="v">${c.unique_count}</span></div></div>`;
    }

    const nullPct = c.null_pct || 0;
    return `
      <div class="col-card" style="animation-delay:${idx * 0.03}s">
        <div class="col-card-head">
          <span class="col-card-name" title="${esc(c.name)}">${esc(c.name)}</span>
          <span class="col-type-badge ${c.type}">${c.type}</span>
        </div>
        ${extra}
        ${nullPct > 0 ? `<div class="null-bar"><div class="null-bar-fill" style="width:${Math.min(nullPct, 100)}%"></div></div>` : ''}
      </div>`;
  }

  // =========================================================================
  // Data preview table (sortable)
  // =========================================================================
  function renderPreview() {
    const pv = state.preview;
    const table = $('#dataTable');
    const cols = pv.columns;
    const colTypes = {};
    state.profile.columns.forEach((c) => { colTypes[c.name] = c.type; });

    // Sort rows if needed.
    let rows = pv.rows;
    if (state.sortCol && rows.length) {
      rows = [...rows].sort((a, b) => {
        let av = a[state.sortCol], bv = b[state.sortCol];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * state.sortDir;
        return String(av).localeCompare(String(bv)) * state.sortDir;
      });
    }

    // Header.
    let html = '<thead><tr>';
    html += '<th class="row-num">#</th>';
    cols.forEach((col) => {
      const t = colTypes[col] || 'categorical';
      const sorted = state.sortCol === col ? 'sorted' : '';
      const arrow = state.sortCol === col ? (state.sortDir > 0 ? '▲' : '▼') : '↕';
      html += `<th class="${sorted}" data-col="${esc(col)}">
        <div class="th-inner">
          <span>${esc(col)}</span>
          <span class="th-type ${t}">${t[0]}</span>
          <span class="sort-icon">${arrow}</span>
        </div>
      </th>`;
    });
    html += '</tr></thead><tbody>';
    rows.forEach((row, i) => {
      html += '<tr>';
      html += `<td class="row-num">${i + 1}</td>`;
      cols.forEach((col) => {
        const v = row[col];
        const cls = v == null ? 'null-cell' : '';
        html += `<td class="${cls}">${v == null ? 'null' : esc(String(v))}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody>';
    table.innerHTML = html;

    // Bind sort on headers.
    table.querySelectorAll('th[data-col]').forEach((th) => {
      th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (state.sortCol === col) {
          state.sortDir *= -1;
        } else {
          state.sortCol = col;
          state.sortDir = 1;
        }
        renderPreview();
      });
    });

    $('#tableNote').textContent = `Showing ${pv.shown} of ${pv.total.toLocaleString()} rows · click column headers to sort`;
    $('#rowsLabel').textContent = `${p_n(state.profile.n_rows)} rows`;
  }

  // =========================================================================
  // Chart suggestions
  // =========================================================================
  function renderChartSuggestions() {
    const container = $('#chartSuggestions');
    if (!state.suggestions.length) {
      container.innerHTML = '<p style="color:var(--text-faint);font-size:.8rem;padding:12px;">No chart suggestions for this data.</p>';
      return;
    }
    const icons = {
      histogram: iconChart('bar', 'c1'),
      scatter: iconChart('scatter', 'c2'),
      bar: iconChart('barv', 'c3'),
      line: iconChart('line', 'c4'),
      box: iconChart('box', 'c1'),
      pie: iconChart('pie', 'c2'),
    };
    container.innerHTML = state.suggestions.map((s) => `
      <div class="suggestion-card" data-id="${s.id}">
        ${icons[s.chart_type] || icons.histogram}
        <div class="sug-title">${esc(s.title)}</div>
        <div class="sug-desc">${esc(s.description)}</div>
      </div>
    `).join('');

    container.querySelectorAll('.suggestion-card').forEach((card) => {
      card.addEventListener('click', () => {
        const s = state.suggestions.find((x) => x.id === card.dataset.id);
        if (s) selectSuggestion(s);
      });
    });
  }

  function selectSuggestion(s) {
    state.activeChart = s;
    $$('.suggestion-card').forEach((c) => c.classList.toggle('active', c.dataset.id === s.id));
    $('#chartTypeSelect').value = s.chart_type;
    updateAxisSelectors(s.chart_type);
    if (s.config.x) $('#xAxisSelect').value = s.config.x;
    if (s.config.y) $('#yAxisSelect').value = s.config.y;
    renderChart(s);
  }

  // =========================================================================
  // Chart rendering
  // =========================================================================
  function populateChartSelectors() {
    const cols = state.profile.columns;
    const numeric = cols.filter((c) => c.type === 'numeric').map((c) => c.name);
    const categorical = cols.filter((c) => c.type === 'categorical').map((c) => c.name);
    const datetime = cols.filter((c) => c.type === 'datetime').map((c) => c.name);
    const all = cols.map((c) => c.name);

    fillSelect($('#colorSelect'), categorical.length ? categorical : all, true);
    // x/y filled dynamically in updateAxisSelectors
  }

  function updateAxisSelectors(chartType) {
    const cols = state.profile.columns;
    const numeric = cols.filter((c) => c.type === 'numeric').map((c) => c.name);
    const categorical = cols.filter((c) => c.type === 'categorical').map((c) => c.name);
    const datetime = cols.filter((c) => c.type === 'datetime').map((c) => c.name);
    const all = cols.map((c) => c.name);

    const xSel = $('#xAxisSelect');
    const ySel = $('#yAxisSelect');
    const colorWrap = $('#colorWrap');

    colorWrap.hidden = true;

    switch (chartType) {
      case 'histogram':
        fillSelect(xSel, numeric.length ? numeric : all);
        ySel.innerHTML = '';
        $('#yAxisWrap').hidden = true;
        break;
      case 'scatter':
        fillSelect(xSel, numeric.length ? numeric : all);
        fillSelect(ySel, numeric.length ? numeric : all);
        $('#yAxisWrap').hidden = false;
        colorWrap.hidden = false;
        const cat = categorical.length ? categorical : all;
        fillSelect($('#colorSelect'), cat, true);
        break;
      case 'bar':
        fillSelect(xSel, categorical.length ? categorical : all);
        fillSelect(ySel, numeric.length ? numeric : all);
        $('#yAxisWrap').hidden = false;
        break;
      case 'line':
        fillSelect(xSel, datetime.length ? datetime : all);
        fillSelect(ySel, numeric.length ? numeric : all);
        $('#yAxisWrap').hidden = false;
        break;
      case 'box':
        fillSelect(xSel, categorical.length ? categorical : all);
        fillSelect(ySel, numeric.length ? numeric : all);
        $('#yAxisWrap').hidden = false;
        break;
      case 'pie':
        fillSelect(xSel, categorical.length ? categorical : all);
        ySel.innerHTML = '';
        $('#yAxisWrap').hidden = true;
        break;
    }
  }

  function fillSelect(sel, options, withEmpty) {
    sel.innerHTML = (withEmpty ? '<option value="">None</option>' : '') +
      options.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
  }

  function bindChartControls() {
    $('#chartTypeSelect').addEventListener('change', (e) => {
      updateAxisSelectors(e.target.value);
    });
    $('#renderChartBtn').addEventListener('click', () => {
      const chartType = $('#chartTypeSelect').value;
      const config = { x: $('#xAxisSelect').value };
      if (!$('#yAxisWrap').hidden) config.y = $('#yAxisSelect').value;
      if (!($('#colorWrap').hidden)) config.color = $('#colorSelect').value || undefined;
      renderChart({
        id: 'custom',
        chart_type: chartType,
        title: $('#chartTypeSelect').selectedOptions[0].text,
        description: 'Custom chart',
        config,
      });
    });
  }

  async function renderChart(suggestion) {
    const container = $('#chartContainer');
    $('#chartTitle').textContent = suggestion.title;

    // Show a subtle loading state inside container.
    container.innerHTML = `<div class="chart-placeholder"><div class="loader-spinner"></div><p>Rendering chart…</p></div>`;

    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/chart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chart_type: suggestion.chart_type,
          config: suggestion.config,
          title: suggestion.title,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Chart failed');

      container.innerHTML = '<div id="plotlyChart" style="width:100%;height:500px;"></div>';
      const plotConfig = {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
      };
      Plotly.newPlot('plotlyChart', data.spec.data, data.spec.layout, plotConfig);
      container.classList.remove('rendered');
      void container.offsetWidth; // reflow to restart animation
      container.classList.add('rendered');
    } catch (e) {
      container.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
    }
  }

  // =========================================================================
  // Clean actions
  // =========================================================================
  function bindClean() {
    // Populate fill-columns select.
    // (done in onSessionLoaded via renderProfile, but also here)
    $$('.clean-action').forEach((btn) => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        const params = {};
        if (action === 'fill_nulls') {
          params.strategy = $('#fillStrategy').value;
          const col = $('#fillColumns').value;
          if (col) params.columns = [col];
        }
        runCleanAction(action, params);
      });
    });
  }

  async function runCleanAction(action, params) {
    showLoader('Applying action…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/clean`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, params }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Clean failed');

      state.profile = data.profile;
      state.preview = data.preview;
      state.suggestions = data.suggestions || [];
      state.history = data.history || [];
      state.sortCol = null;
      state.qualityReport = null; // Clear cached report
      state.correlationReport = null; // Clear cached correlation
      state.distributionReport = null; // Clear cached distribution

      renderProfile();
      renderPreview();
      renderChartSuggestions();
      renderHistory();
      populateCleanSelects();
      if (state.suggestions.length) selectSuggestion(state.suggestions[0]);

      const labels = {
        fill_nulls: 'Filled null values',
        drop_duplicates: 'Dropped duplicate rows',
        strip_whitespace: 'Stripped whitespace',
        drop_nulls: 'Dropped null rows',
        reset: 'Reset to original data',
      };
      const beforeRows = state.profile.n_rows;
      showToast(`${labels[action] || action} — ${beforeRows.toLocaleString()} rows now`, 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  function populateCleanSelects() {
    const cols = state.profile.columns;
    const fillSel = $('#fillColumns');
    const current = fillSel.value;
    fillSel.innerHTML = '<option value="">All columns</option>' +
      cols.map((c) => `<option value="${esc(c.name)}">${esc(c.name)} (${c.type})</option>`).join('');
    fillSel.value = current;

    // Update duplicate stat.
    const dupStat = $('#dupStat');
    if (state.profile.duplicate_rows > 0) {
      dupStat.innerHTML = `<span style="color:var(--orange)">${state.profile.duplicate_rows} duplicate rows found</span>`;
    } else {
      dupStat.innerHTML = `<span style="color:var(--green)">No duplicates found</span>`;
    }
  }

  function renderHistory() {
    const wrap = $('#cleanHistory');
    const list = $('#historyList');
    populateCleanSelects();
    if (!state.history.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    list.innerHTML = state.history.map((h) => {
      const labels = {
        fill_nulls: 'Fill nulls',
        drop_duplicates: 'Drop duplicates',
        strip_whitespace: 'Strip whitespace',
        drop_nulls: 'Drop null rows',
        reset: 'Reset to original',
      };
      const time = new Date(h.at).toLocaleTimeString();
      return `<div class="history-item"><span class="h-dot"></span><span class="h-action">${labels[h.action] || h.action}</span><span class="h-time">${time}</span></div>`;
    }).join('');
  }

  // =========================================================================
  // Data Quality Report
  // =========================================================================
  async function loadQualityReport() {
    const container = $('#reportContainer');
    if (!state.sessionId) return;
    
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/quality-report`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load report');
      
      state.qualityReport = data;
      renderQualityReport(data);
    } catch (e) {
      container.innerHTML = `<div class="report-error"><p>Error loading report: ${esc(e.message)}</p></div>`;
    }
  }

  function renderQualityReport(report) {
    const container = $('#reportContainer');
    
    if (!report || !report.health_score) {
      container.innerHTML = `
        <div class="report-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 11H7.5A1.5 1.5 0 006 9.5V6a2 2 0 012-2h8a2 2 0 012 2v3.5A1.5 1.5 0 0116.5 11H15"/>
            <line x1="4" y1="20" x2="20" y2="20"/>
          </svg>
          <p>No quality report data available.</p>
        </div>
      `;
      return;
    }
    
    let html = '<div class="report-wrapper">';
    
    // Health Score Section with status badge
    html += renderHealthScoreSection(report.health_score);
    
    // Dataset Overview
    html += renderDatasetOverviewSection(report.dataset_overview);
    
    // Missing Value Analysis
    if (report.missing_value_analysis.columns.length > 0) {
      html += renderMissingValueSection(report.missing_value_analysis);
    }
    
    // Duplicate Analysis
    html += renderDuplicateAnalysisSection(report.duplicate_analysis);
    
    // Data Type Analysis
    if (report.datatype_analysis.columns.length > 0) {
      html += renderDatatypeAnalysisSection(report.datatype_analysis);
    }
    
    // Unique Value Analysis
    html += renderUniqueValueAnalysisSection(report.unique_value_analysis);
    
    // Invalid Data Detection
    if (report.invalid_data_detection.columns.length > 0) {
      html += renderInvalidDataSection(report.invalid_data_detection);
    }
    
    // Column Quality Table
    if (report.unique_value_analysis && report.unique_value_analysis.columns) {
      html += renderColumnQualityTable(report.unique_value_analysis.columns);
    }
    
    // Recommendations
    if (report.recommendations.length > 0) {
      html += renderRecommendationsSection(report.recommendations);
    }
    
    html += '</div>';
    container.innerHTML = html;
    
    // Post-render: initialize Plotly charts (innerHTML doesn't execute inline scripts)
    requestAnimationFrame(() => initReportCharts(report));
  }

  function initReportCharts(report) {
    // Render missing value chart
    const missingChart = document.getElementById('missingValueChart');
    if (missingChart && report.missing_value_analysis && report.missing_value_analysis.columns.length > 0) {
      const cols = report.missing_value_analysis.columns;
      const trace = {
        x: cols.map(c => c.name),
        y: cols.map(c => c.null_count),
        type: 'bar',
        marker: { color: cols.map(c => c.null_pct > 50 ? '#f87171' : c.null_pct > 20 ? '#f0a35e' : '#7c9cff') },
        text: cols.map(c => c.null_pct + '%'),
        textposition: 'outside',
        hovertemplate: '<b>%{x}</b><br>Missing: %{y}<br>%{text}<extra></extra>'
      };
      const layout = {
        margin: { t: 20, r: 20, b: 80, l: 60 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Inter, system-ui', color: '#8b949e', size: 11 },
        xaxis: { tickangle: -45, gridcolor: '#21262d' },
        yaxis: { gridcolor: '#21262d', title: 'Missing Count' },
        height: 300
      };
      Plotly.newPlot('missingValueChart', [trace], layout, { responsive: true, displayModeBar: false });
    }
  }

  function renderColumnQualityTable(columns) {
    if (!columns || columns.length === 0) return '';
    
    const rows = columns.map(col => {
      let scoreClass = 'score-excellent';
      if (col.quality_score < 50) scoreClass = 'score-poor';
      else if (col.quality_score < 75) scoreClass = 'score-average';
      else if (col.quality_score < 90) scoreClass = 'score-good';
      
      return `
        <tr>
          <td>${esc(col.name)}</td>
          <td><span class="type-badge ${col.type}">${col.type}</span></td>
          <td>${col.unique_count}</td>
          <td>${col.unique_pct}%</td>
          <td>
            <div class="quality-score-bar">
              <div class="quality-score-fill ${scoreClass}" style="width:${col.quality_score}%"></div>
            </div>
            <span class="quality-score-text ${scoreClass}">${col.quality_score}</span>
          </td>
        </tr>
      `;
    }).join('');
    
    return `
      <div class="report-section">
        <h2 class="report-title">Column Quality Scores</h2>
        <table class="report-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Unique Values</th>
              <th>Cardinality</th>
              <th>Quality Score</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderHealthScoreSection(healthScore) {
    const status = healthScore.status;
    const score = healthScore.score;
    let statusColor = 'var(--green)';
    let statusClass = 'badge-excellent';
    if (status === 'Good') { statusColor = 'var(--green)'; statusClass = 'badge-good'; }
    else if (status === 'Average') { statusColor = 'var(--orange)'; statusClass = 'badge-average'; }
    else if (status === 'Poor') { statusColor = 'var(--red)'; statusClass = 'badge-poor'; }
    else if (status === 'Excellent') { statusColor = 'var(--green)'; statusClass = 'badge-excellent'; }
    
    const breakdown = healthScore.breakdown;
    
    return `
      <div class="report-section">
        <h2 class="report-title">Data Quality Score</h2>
        <div class="health-score-card">
          <div class="health-score-display">
            <div class="health-score-circle" style="--health-score: ${score}%;">
              <div class="health-score-number">${score}</div>
            </div>
            <div class="health-score-status-badge ${statusClass}">${status}</div>
          </div>
          <div class="health-breakdown">
            <div class="breakdown-item">
              <span class="breakdown-label">Completeness</span>
              <div class="breakdown-bar"><div class="breakdown-fill" style="width:${breakdown.completeness}%;"></div></div>
              <span class="breakdown-value">${breakdown.completeness}</span>
            </div>
            <div class="breakdown-item">
              <span class="breakdown-label">Validity</span>
              <div class="breakdown-bar"><div class="breakdown-fill" style="width:${breakdown.validity}%;"></div></div>
              <span class="breakdown-value">${breakdown.validity}</span>
            </div>
            <div class="breakdown-item">
              <span class="breakdown-label">Consistency</span>
              <div class="breakdown-bar"><div class="breakdown-fill" style="width:${breakdown.consistency}%;"></div></div>
              <span class="breakdown-value">${breakdown.consistency}</span>
            </div>
            <div class="breakdown-item">
              <span class="breakdown-label">Accuracy</span>
              <div class="breakdown-bar"><div class="breakdown-fill" style="width:${breakdown.accuracy}%;"></div></div>
              <span class="breakdown-value">${breakdown.accuracy}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderDatasetOverviewSection(overview) {
    return `
      <div class="report-section">
        <h2 class="report-title">Dataset Overview</h2>
        <div class="overview-grid">
          <div class="overview-card">
            <div class="overview-label">Total Rows</div>
            <div class="overview-value">${p_n(overview.total_rows)}</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">Total Columns</div>
            <div class="overview-value">${overview.total_columns}</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">Memory Usage</div>
            <div class="overview-value">${overview.memory_mb} MB</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">Dataset Size</div>
            <div class="overview-value">${overview.dataset_size}</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">Numeric Columns</div>
            <div class="overview-value">${overview.numeric_columns}</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">Categorical Columns</div>
            <div class="overview-value">${overview.categorical_columns}</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">DateTime Columns</div>
            <div class="overview-value">${overview.datetime_columns}</div>
          </div>
          <div class="overview-card">
            <div class="overview-label">Boolean Columns</div>
            <div class="overview-value">${overview.boolean_columns || 0}</div>
          </div>
        </div>
      </div>
    `;
  }

  function renderMissingValueSection(missingAnalysis) {
    const rows = missingAnalysis.columns.map(col => `
      <tr>
        <td>${esc(col.name)}</td>
        <td>${col.null_count}</td>
        <td><div class="progress-bar"><div class="progress-fill" style="width:${Math.min(col.null_pct, 100)}%"></div></div></td>
        <td>${col.null_pct}%</td>
      </tr>
    `).join('');
    
    const chartId = 'missingValueChart';
    const chartData = {
      names: missingAnalysis.columns.map(c => c.name),
      counts: missingAnalysis.columns.map(c => c.null_count),
      pcts: missingAnalysis.columns.map(c => c.null_pct),
    };
    
    return `
      <div class="report-section">
        <h2 class="report-title">Missing Value Analysis</h2>
        <div class="report-stat">
          <span class="report-stat-label">Overall Missing:</span>
          <span class="report-stat-value">${missingAnalysis.overall_null_pct}%</span>
        </div>
        ${missingAnalysis.columns.length > 0 ? `
          <div class="report-chart-wrapper">
            <div id="${chartId}" class="report-plotly-chart" data-chart='chart-missing'></div>
          </div>
        ` : ''}
        <table class="report-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Count</th>
              <th>Distribution</th>
              <th>Percentage</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderDuplicateAnalysisSection(duplicateAnalysis) {
    let html = `
      <div class="report-section">
        <h2 class="report-title">Duplicate Analysis</h2>
        <div class="duplicate-stats">
          <div class="stat-box">
            <div class="stat-box-label">Duplicate Rows</div>
            <div class="stat-box-value">${duplicateAnalysis.duplicate_rows}</div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Duplicate Percentage</div>
            <div class="stat-box-value">${duplicateAnalysis.duplicate_pct}%</div>
          </div>
        </div>
    `;
    
    if (duplicateAnalysis.duplicate_columns && duplicateAnalysis.duplicate_columns.length > 0) {
      html += `
        <div class="duplicate-cols">
          <h3>Duplicate Columns</h3>
          <ul>
            ${duplicateAnalysis.duplicate_columns.map(d => `<li>${esc(d.column1)} ↔ ${esc(d.column2)}</li>`).join('')}
          </ul>
        </div>
      `;
    }
    
    html += '</div>';
    return html;
  }

  function renderDatatypeAnalysisSection(datatypeAnalysis) {
    const rows = datatypeAnalysis.columns.map(col => {
      const hasMismatch = col.suggested_datatype && col.suggested_datatype !== col.detected_type;
      const mixedBadge = col.is_mixed_type ? '<span class="status-badge badge-warning">Mixed Types</span>' : '';
      const suggestionBadge = hasMismatch ? `<span class="status-badge badge-info" title="Suggested: ${col.suggested_datatype}">Suggests: ${col.suggested_datatype}</span>` : '';
      return `
      <tr>
        <td>${esc(col.name)}</td>
        <td><span class="type-badge ${col.detected_type}">${col.detected_type}</span></td>
        <td>${hasMismatch ? `<span class="type-badge ${col.suggested_datatype}">${col.suggested_datatype}</span>` : '<span class="text-dim">—</span>'}</td>
        <td>${col.invalid_count}</td>
        <td>${col.invalid_reason || '—'}</td>
        <td>${mixedBadge}${suggestionBadge}</td>
      </tr>
    `}).join('');
    
    return `
      <div class="report-section">
        <h2 class="report-title">Data Type Analysis</h2>
        <table class="report-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Detected Type</th>
              <th>Suggested Type</th>
              <th>Invalid Count</th>
              <th>Issue</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderUniqueValueAnalysisSection(uniqueAnalysis) {
    let html = '<div class="report-section"><h2 class="report-title">Unique Value Analysis</h2>';
    
    if (uniqueAnalysis.constant_columns && uniqueAnalysis.constant_columns.length > 0) {
      html += `
        <div class="analysis-subsection">
          <h3>Constant Columns</h3>
          <ul class="column-list">
            ${uniqueAnalysis.constant_columns.map(c => `<li>${esc(c.name)} <span class="badge">${c.type}</span></li>`).join('')}
          </ul>
        </div>
      `;
    }
    
    if (uniqueAnalysis.near_constant_columns && uniqueAnalysis.near_constant_columns.length > 0) {
      html += `
        <div class="analysis-subsection">
          <h3>Near-Constant Columns</h3>
          <ul class="column-list">
            ${uniqueAnalysis.near_constant_columns.map(c => `<li>${esc(c.name)} <span class="badge">${c.unique_count} unique (${c.unique_pct}%)</span></li>`).join('')}
          </ul>
        </div>
      `;
    }
    
    if (uniqueAnalysis.high_cardinality_columns && uniqueAnalysis.high_cardinality_columns.length > 0) {
      html += `
        <div class="analysis-subsection">
          <h3>High-Cardinality Columns</h3>
          <ul class="column-list">
            ${uniqueAnalysis.high_cardinality_columns.map(c => `<li>${esc(c.name)} <span class="badge warning">${c.unique_count} unique (${c.unique_pct}%)</span></li>`).join('')}
          </ul>
        </div>
      `;
    }
    
    html += '</div>';
    return html;
  }

  function renderInvalidDataSection(invalidAnalysis) {
    let html = `
      <div class="report-section">
        <h2 class="report-title">Invalid Data Detection</h2>
        <div class="invalid-stats">
          <div class="stat-box">
            <div class="stat-box-label">Invalid Values</div>
            <div class="stat-box-value">${invalidAnalysis.total_invalid}</div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Empty Cells</div>
            <div class="stat-box-value">${invalidAnalysis.total_empty}</div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Whitespace Only</div>
            <div class="stat-box-value">${invalidAnalysis.total_whitespace}</div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Negative Values</div>
            <div class="stat-box-value">${invalidAnalysis.total_negative || 0}</div>
          </div>
        </div>
    `;
    
    if (invalidAnalysis.columns && invalidAnalysis.columns.length > 0) {
      const rows = invalidAnalysis.columns.map(col => `
        <tr>
          <td>${esc(col.name)}</td>
          <td><span class="type-badge ${col.type}">${col.type}</span></td>
          <td>${col.invalid_count}</td>
          <td>${col.empty_count}</td>
          <td>${col.whitespace_count}</td>
          <td>${col.negative_count || 0}</td>
        </tr>
      `).join('');
      
      html += `
        <table class="report-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Invalid</th>
              <th>Empty</th>
              <th>Whitespace</th>
              <th>Negative</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      `;
    }
    
    html += '</div>';
    return html;
  }

  function renderRecommendationsSection(recommendations) {
    const priorityColors = {
      critical: 'var(--red)',
      high: 'var(--orange)',
      medium: 'var(--accent)',
      low: 'var(--green)',
    };
    
    const recItems = recommendations.map(rec => `
      <div class="rec-card" style="border-left-color: ${priorityColors[rec.priority] || 'var(--text-faint)'};">
        <div class="rec-header">
          <span class="rec-priority" style="background: ${priorityColors[rec.priority] || 'var(--text-faint)'};">${rec.priority}</span>
          <h3 class="rec-title">${esc(rec.title)}</h3>
        </div>
        <p class="rec-description">${esc(rec.description)}</p>
        ${rec.affected_columns ? `<div class="rec-cols"><strong>Affected:</strong> ${rec.affected_columns.map(c => `<span class="col-tag">${esc(c)}</span>`).join('')}</div>` : ''}
      </div>
    `).join('');
    
    return `
      <div class="report-section">
        <h2 class="report-title">Recommendations</h2>
        <div class="recommendations-list">
          ${recItems}
        </div>
      </div>
    `;
  }

  // =========================================================================
  // Advanced Correlation Analysis
  // =========================================================================
  async function loadCorrelationReport(method) {
    const container = $('#correlationContainer');
    if (!state.sessionId) return;

    const m = method || 'pearson';
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/correlation?method=${m}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load correlation');

      state.correlationReport = data;
      renderCorrelationReport(data);
    } catch (e) {
      container.innerHTML = `<div class="report-error"><p>Error loading correlation: ${esc(e.message)}</p></div>`;
    }
  }

  function renderCorrelationReport(report) {
    const container = $('#correlationContainer');

    if (report.error) {
      container.innerHTML = `
        <div class="corr-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <rect x="7" y="7" width="3" height="3"/>
            <rect x="14" y="7" width="3" height="3"/>
            <rect x="7" y="14" width="3" height="3"/>
            <rect x="14" y="14" width="3" height="3"/>
          </svg>
          <p>${esc(report.error)}</p>
        </div>
      `;
      return;
    }

    let html = '<div class="corr-wrapper">';

    // Summary cards
    html += renderCorrSummaryCards(report);

    // Method selector + export
    html += renderCorrControls(report);

    // Heatmap
    html += '<div class="corr-section"><h2 class="report-title">Correlation Heatmap</h2>';
    html += '<div class="corr-heatmap-wrap"><div id="corrHeatmap" class="corr-plotly-chart"></div></div>';
    html += '</div>';

    // Top correlations
    html += renderCorrTopSection(report);

    // Correlation table
    html += renderCorrTable(report);

    // Scatter plot
    html += '<div class="corr-section"><h2 class="report-title">Pairwise Scatter Plot</h2>';
    html += '<div class="corr-scatter-controls">';
    html += '<label class="select-label">Feature A <select id="corrScatterA"></select></label>';
    html += '<label class="select-label">Feature B <select id="corrScatterB"></select></label>';
    html += '<button id="corrScatterBtn" class="btn btn-primary btn-sm">Plot</button>';
    html += '</div>';
    html += '<div id="corrScatterPlot" class="corr-plotly-chart"></div>';
    html += '</div>';

    // Network graph
    html += '<div class="corr-section"><h2 class="report-title">Correlation Network Graph</h2>';
    html += '<div id="corrNetwork" class="corr-plotly-chart"></div>';
    html += '</div>';

    // AI Insights
    if (report.insights && report.insights.length) {
      html += renderCorrInsights(report.insights);
    }

    // Recommendations
    if (report.recommendations && report.recommendations.length) {
      html += renderCorrRecommendations(report.recommendations);
    }

    // Multicollinearity warnings
    if (report.multicollinearity && report.multicollinearity.length) {
      html += renderMulticollinearityWarnings(report.multicollinearity);
    }

    html += '</div>';
    container.innerHTML = html;

    // Initialize all charts and controls
    requestAnimationFrame(() => initCorrelationUI(report));
  }

  function renderCorrSummaryCards(report) {
    const n = report.num_numeric_columns;
    const totalPairs = report.pairs ? report.pairs.length : 0;
    const strongPairs = report.pairs ? report.pairs.filter(p => p.abs_value >= 0.7).length : 0;
    const mcCount = report.multicollinearity ? report.multicollinearity.length : 0;
    return `
      <div class="corr-section">
        <h2 class="report-title">Correlation Summary</h2>
        <div class="corr-summary-grid">
          <div class="stat-box"><div class="stat-box-label">Numeric Columns</div><div class="stat-box-value">${n}</div></div>
          <div class="stat-box"><div class="stat-box-label">Total Pairs</div><div class="stat-box-value">${totalPairs}</div></div>
          <div class="stat-box"><div class="stat-box-label">Strong Correlations</div><div class="stat-box-value" style="color:var(--green)">${strongPairs}</div></div>
          <div class="stat-box"><div class="stat-box-label">Multicollinear</div><div class="stat-box-value" style="color:${mcCount > 0 ? 'var(--red)' : 'var(--green)'}">${mcCount}</div></div>
        </div>
      </div>
    `;
  }

  function renderCorrControls(report) {
    return `
      <div class="corr-section">
        <div class="corr-controls-bar">
          <div class="corr-method-group">
            <label class="select-label">Method
              <select id="corrMethodSelect">
                <option value="pearson" ${report.method === 'pearson' ? 'selected' : ''}>Pearson</option>
                <option value="spearman" ${report.method === 'spearman' ? 'selected' : ''}>Spearman</option>
                <option value="kendall" ${report.method === 'kendall' ? 'selected' : ''}>Kendall Tau</option>
              </select>
            </label>
            <button id="corrRecalcBtn" class="btn btn-primary btn-sm">Recalculate</button>
          </div>
          <div class="corr-export-group">
            <button class="btn btn-ghost btn-sm corr-export" data-format="csv">CSV</button>
            <button class="btn btn-ghost btn-sm corr-export" data-format="json">JSON</button>
          </div>
        </div>
      </div>
    `;
  }

  function renderCorrTopSection(report) {
    let html = '<div class="corr-section"><h2 class="report-title">Top Correlations</h2>';

    // Positive
    html += '<h3 class="corr-subtitle">Top Positive</h3>';
    if (report.top_positive && report.top_positive.length) {
      html += '<div class="corr-top-list">';
      report.top_positive.forEach(p => {
        html += `<div class="corr-top-item" data-a="${esc(p.feature_a)}" data-b="${esc(p.feature_b)}">
          <span class="corr-top-pair">${esc(p.feature_a)} ↔ ${esc(p.feature_b)}</span>
          <span class="corr-top-val" style="color:var(--green)">+${p.value.toFixed(4)}</span>
          <span class="corr-strength-badge" style="background:${p.badge_color}22;color:${p.badge_color}">${p.strength}</span>
        </div>`;
      });
      html += '</div>';
    } else {
      html += '<p class="text-dim">No positive correlations found.</p>';
    }

    // Negative
    html += '<h3 class="corr-subtitle">Top Negative</h3>';
    if (report.top_negative && report.top_negative.length) {
      html += '<div class="corr-top-list">';
      report.top_negative.forEach(p => {
        html += `<div class="corr-top-item" data-a="${esc(p.feature_a)}" data-b="${esc(p.feature_b)}">
          <span class="corr-top-pair">${esc(p.feature_a)} ↔ ${esc(p.feature_b)}</span>
          <span class="corr-top-val" style="color:var(--red)">${p.value.toFixed(4)}</span>
          <span class="corr-strength-badge" style="background:${p.badge_color}22;color:${p.badge_color}">${p.strength}</span>
        </div>`;
      });
      html += '</div>';
    } else {
      html += '<p class="text-dim">No negative correlations found.</p>';
    }

    // Most independent
    html += '<h3 class="corr-subtitle">Most Independent Features</h3>';
    if (report.independent_features && report.independent_features.length) {
      html += '<div class="corr-top-list">';
      report.independent_features.slice(0, 5).forEach(p => {
        html += `<div class="corr-top-item" data-a="${esc(p.feature_a)}" data-b="${esc(p.feature_b)}">
          <span class="corr-top-pair">${esc(p.feature_a)} ↔ ${esc(p.feature_b)}</span>
          <span class="corr-top-val">${p.value.toFixed(4)}</span>
          <span class="corr-strength-badge" style="background:#6e768122;color:#6e7681">${p.strength}</span>
        </div>`;
      });
      html += '</div>';
    }

    // Most influential
    html += '<h3 class="corr-subtitle">Most Influential Columns</h3>';
    if (report.influential_columns && report.influential_columns.length) {
      html += '<div class="corr-top-list">';
      report.influential_columns.slice(0, 5).forEach(c => {
        html += `<div class="corr-top-item">
          <span class="corr-top-pair">${esc(c.name)}</span>
          <span class="corr-top-val">avg |r| = ${c.avg_corr.toFixed(4)}</span>
        </div>`;
      });
      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  function renderCorrTable(report) {
    if (!report.pairs || !report.pairs.length) return '';

    let filterHtml = `
      <div class="corr-filter-bar">
        <label class="select-label">Min Correlation
          <input type="number" id="corrFilterMin" class="corr-filter-input" value="0" min="0" max="1" step="0.1">
        </label>
        <label class="select-label">Search
          <input type="text" id="corrFilterSearch" class="corr-filter-input" placeholder="Search features...">
        </label>
        <div class="corr-filter-toggles">
          <button class="btn btn-sm corr-toggle active" data-filter="all">All</button>
          <button class="btn btn-sm corr-toggle" data-filter="positive">Positive</button>
          <button class="btn btn-sm corr-toggle" data-filter="negative">Negative</button>
          <button class="btn btn-sm corr-toggle" data-filter="strong">Strong</button>
        </div>
      </div>
    `;

    let html = `<div class="corr-section"><h2 class="report-title">Correlation Matrix Table</h2>${filterHtml}`;
    html += '<div class="corr-table-wrap"><table class="report-table" id="corrTable"><thead><tr>';
    html += '<th>Feature A</th><th>Feature B</th><th>Correlation</th><th>Strength</th><th>Direction</th>';
    html += '</tr></thead><tbody id="corrTableBody">';

    report.pairs.forEach(p => {
      html += `<tr class="corr-row" data-val="${p.value}" data-a="${esc(p.feature_a)}" data-b="${esc(p.feature_b)}" data-dir="${p.direction}" data-str="${p.strength}">
        <td>${esc(p.feature_a)}</td>
        <td>${esc(p.feature_b)}</td>
        <td style="color:${p.value >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:700;font-family:var(--mono)">${p.value.toFixed(4)}</td>
        <td><span class="corr-strength-badge" style="background:${p.badge_color}22;color:${p.badge_color}">${p.strength}</span></td>
        <td>${p.direction}</td>
      </tr>`;
    });

    html += '</tbody></table></div></div>';
    return html;
  }

  function renderCorrInsights(insights) {
    const items = insights.map(i => `<div class="corr-insight-item">${esc(i)}</div>`).join('');
    return `
      <div class="corr-section">
        <h2 class="report-title">AI Insights</h2>
        <div class="corr-insights-list">${items}</div>
      </div>
    `;
  }

  function renderCorrRecommendations(recs) {
    const priorityColors = {
      critical: 'var(--red)', high: 'var(--orange)',
      medium: 'var(--accent)', low: 'var(--green)',
    };
    const items = recs.map(r => `
      <div class="rec-card" style="border-left-color:${priorityColors[r.priority] || 'var(--text-faint)'}">
        <div class="rec-header">
          <span class="rec-priority" style="background:${priorityColors[r.priority] || 'var(--text-faint)'}">${r.priority}</span>
          <h3 class="rec-title">${esc(r.title)}</h3>
        </div>
        <p class="rec-description">${esc(r.description)}</p>
        ${r.affected_columns ? `<div class="rec-cols"><strong>Affected:</strong> ${r.affected_columns.map(c => `<span class="col-tag">${esc(c)}</span>`).join('')}</div>` : ''}
      </div>
    `).join('');
    return `
      <div class="corr-section">
        <h2 class="report-title">Recommendations</h2>
        <div class="recommendations-list">${items}</div>
      </div>
    `;
  }

  function renderMulticollinearityWarnings(mc) {
    const items = mc.map(m => `
      <div class="corr-mc-item">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <span><strong>${esc(m.feature_a)}</strong> ↔ <strong>${esc(m.feature_b)}</strong>: r = ${m.value.toFixed(4)}</span>
      </div>
    `).join('');
    return `
      <div class="corr-section">
        <h2 class="report-title">Multicollinearity Warnings</h2>
        <div class="corr-mc-list">${items}</div>
      </div>
    `;
  }

  function initCorrelationUI(report) {
    if (!report || report.error) return;

    // Method selector
    const methodSelect = document.getElementById('corrMethodSelect');
    const recalcBtn = document.getElementById('corrRecalcBtn');
    if (methodSelect && recalcBtn) {
      recalcBtn.addEventListener('click', () => {
        state.correlationReport = null;
        loadCorrelationReport(methodSelect.value);
      });
    }

    // Export buttons
    document.querySelectorAll('.corr-export').forEach(btn => {
      btn.addEventListener('click', () => {
        exportCorrelation(btn.dataset.format);
      });
    });

    // Heatmap
    if (report.matrix) {
      fetch(`${API}/api/session/${state.sessionId}/correlation/heatmap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec: report.matrix, title: `Correlation Heatmap (${report.method})` }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.spec) {
            Plotly.newPlot('corrHeatmap', data.spec.data, data.spec.layout, {
              responsive: true, displayModeBar: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d'],
              displaylogo: false,
            });
          }
        })
        .catch(() => {});
    }

    // Scatter plot controls
    if (report.numeric_columns && report.numeric_columns.length >= 2) {
      const selA = document.getElementById('corrScatterA');
      const selB = document.getElementById('corrScatterB');
      const scatterBtn = document.getElementById('corrScatterBtn');
      if (selA && selB) {
        const opts = report.numeric_columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
        selA.innerHTML = opts;
        selB.innerHTML = opts;
        if (report.numeric_columns.length > 1) selB.selectedIndex = 1;

        if (scatterBtn) {
          scatterBtn.addEventListener('click', () => renderCorrelationScatter(selA.value, selB.value));
        }

        // Auto-render first pair
        if (report.pairs && report.pairs.length) {
          renderCorrelationScatter(report.pairs[0].feature_a, report.pairs[0].feature_b);
        }
      }
    }

    // Network graph
    if (report.network && report.network.nodes.length) {
      fetch(`${API}/api/session/${state.sessionId}/correlation/network`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ network: report.network }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.spec) {
            Plotly.newPlot('corrNetwork', data.spec.data, data.spec.layout, {
              responsive: true, displayModeBar: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d'],
              displaylogo: false, scrollZoom: true,
            });
          }
        })
        .catch(() => {});
    }

    // Filter controls
    bindCorrFilters();

    // Top item click -> scatter
    document.querySelectorAll('.corr-top-item[data-a]').forEach(item => {
      item.addEventListener('click', () => {
        const a = item.dataset.a;
        const b = item.dataset.b;
        const selA = document.getElementById('corrScatterA');
        const selB = document.getElementById('corrScatterB');
        if (selA && selB && a && b) {
          selA.value = a;
          selB.value = b;
          renderCorrelationScatter(a, b);
        }
      });
    });
  }

  async function renderCorrelationScatter(colA, colB) {
    const plotDiv = document.getElementById('corrScatterPlot');
    if (!plotDiv) return;
    plotDiv.innerHTML = '<div class="chart-placeholder"><div class="loader-spinner"></div></div>';

    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/correlation/scatter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ col_a: colA, col_b: colB }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      plotDiv.innerHTML = '';
      Plotly.newPlot('corrScatterPlot', data.spec.data, data.spec.layout, {
        responsive: true, displayModeBar: true, displaylogo: false,
      });
    } catch (e) {
      plotDiv.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
    }
  }

  function bindCorrFilters() {
    const filterMin = document.getElementById('corrFilterMin');
    const filterSearch = document.getElementById('corrFilterSearch');
    const toggles = document.querySelectorAll('.corr-toggle');
    const rows = document.querySelectorAll('.corr-row');

    function applyFilters() {
      const minVal = parseFloat(filterMin ? filterMin.value : 0) || 0;
      const search = filterSearch ? filterSearch.value.toLowerCase() : '';
      const activeToggle = document.querySelector('.corr-toggle.active');
      const filterType = activeToggle ? activeToggle.dataset.filter : 'all';

      rows.forEach(row => {
        const val = parseFloat(row.dataset.val);
        const a = row.dataset.a.toLowerCase();
        const b = row.dataset.b.toLowerCase();
        const dir = row.dataset.dir;
        const str = row.dataset.str;

        let show = true;
        if (Math.abs(val) < minVal) show = false;
        if (search && !a.includes(search) && !b.includes(search)) show = false;
        if (filterType === 'positive' && dir !== 'Positive') show = false;
        if (filterType === 'negative' && dir !== 'Negative') show = false;
        if (filterType === 'strong' && (str !== 'Very Strong' && str !== 'Strong')) show = false;

        row.style.display = show ? '' : 'none';
      });
    }

    if (filterMin) filterMin.addEventListener('input', applyFilters);
    if (filterSearch) filterSearch.addEventListener('input', applyFilters);
    toggles.forEach(t => {
      t.addEventListener('click', () => {
        toggles.forEach(x => x.classList.remove('active'));
        t.classList.add('active');
        applyFilters();
      });
    });
  }

  function exportCorrelation(format) {
    if (!state.correlationReport || !state.correlationReport.pairs) return;
    const pairs = state.correlationReport.pairs;

    fetch(`${API}/api/session/${state.sessionId}/correlation/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, pairs }),
    })
      .then(r => {
        const disp = r.headers.get('Content-Disposition');
        const ext = format === 'json' ? 'json' : 'csv';
        return r.text().then(text => ({ text, ext }));
      })
      .then(({ text, ext }) => {
        const blob = new Blob([text], { type: ext === 'json' ? 'application/json' : 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `correlation.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showToast(`Exported correlation as ${ext.toUpperCase()}`, 'success');
      })
      .catch(e => showToast('Export failed: ' + e.message, 'error'));
  }

  // =========================================================================
  // Advanced Distribution Analysis
  // =========================================================================
  async function loadDistributionReport() {
    const container = $('#distributionContainer');
    if (!state.sessionId) return;

    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/distribution`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load distribution');

      state.distributionReport = data;
      renderDistributionReport(data);
    } catch (e) {
      container.innerHTML = `<div class="report-error"><p>Error loading distribution: ${esc(e.message)}</p></div>`;
    }
  }

  function renderDistributionReport(report) {
    const container = $('#distributionContainer');

    if (report.error) {
      container.innerHTML = `
        <div class="dist-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 20h18M5 20V10M9 20V4M13 20V8M17 20V6M21 20V12"/>
          </svg>
          <p>${esc(report.error)}</p>
        </div>
      `;
      return;
    }

    let html = '<div class="dist-wrapper">';

    // Summary dashboard
    html += renderDistSummaryCards(report);

    // Controls: column selector, chart type, export
    html += renderDistControls(report);

    // Distribution charts grid
    html += '<div class="dist-section"><h2 class="report-title">Distribution Charts</h2>';
    html += '<div class="dist-charts-grid">';
    html += '<div id="distMainChart" class="dist-plotly-chart"></div>';
    html += '<div id="distKdeChart" class="dist-plotly-chart"></div>';
    html += '<div id="distBoxChart" class="dist-plotly-chart"></div>';
    html += '<div id="distViolinChart" class="dist-plotly-chart"></div>';
    html += '</div></div>';

    // Descriptive statistics table
    html += renderDistDescriptiveTable(report);

    // Shape analysis
    html += renderDistShapeSection(report);

    // Normality tests
    html += renderDistNormalitySection(report);

    // Percentile analysis
    html += renderDistPercentileSection(report);

    // Column quality scores
    html += renderDistQualityScores(report);

    // Interactive filters
    html += renderDistFilters(report);

    // Distribution comparison
    html += renderDistComparison(report);

    // Transformation preview
    html += renderDistTransform(report);

    // AI Insights
    if (report.insights && report.insights.length) {
      html += renderDistInsights(report.insights);
    }

    // Recommendations
    if (report.recommendations && report.recommendations.length) {
      html += renderDistRecommendations(report.recommendations);
    }

    // Export
    html += renderDistExport();

    html += '</div>';
    container.innerHTML = html;

    requestAnimationFrame(() => initDistributionUI(report));
  }

  function renderDistSummaryCards(report) {
    const s = report.summary;
    return `
      <div class="dist-section">
        <h2 class="report-title">Distribution Summary</h2>
        <div class="dist-summary-grid">
          <div class="stat-box"><div class="stat-box-label">Numeric Columns</div><div class="stat-box-value">${s.total_numeric}</div></div>
          <div class="stat-box"><div class="stat-box-label">Normally Distributed</div><div class="stat-box-value" style="color:var(--green)">${s.normal_columns}</div></div>
          <div class="stat-box"><div class="stat-box-label">Skewed</div><div class="stat-box-value" style="color:var(--orange)">${s.skewed_columns}</div></div>
          <div class="stat-box"><div class="stat-box-label">Symmetric</div><div class="stat-box-value" style="color:var(--accent)">${s.symmetric_columns}</div></div>
          <div class="stat-box"><div class="stat-box-label">With Outliers</div><div class="stat-box-value" style="color:${s.columns_with_outliers > 0 ? 'var(--red)' : 'var(--green)'}">${s.columns_with_outliers}</div></div>
          <div class="stat-box">
            <div class="stat-box-label">Quality Score</div>
            <div class="stat-box-value">
              <span class="dist-quality-badge dist-q-${s.avg_quality_status.toLowerCase()}">${s.avg_quality_score} — ${s.avg_quality_status}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderDistControls(report) {
    const cols = report.numeric_columns;
    const opts = cols.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    return `
      <div class="dist-section">
        <div class="dist-controls-bar">
          <div class="dist-control-group">
            <label class="select-label">Column
              <select id="distColumnSelect">${opts}</select>
            </label>
            <label class="select-label">Chart Type
              <select id="distChartTypeSelect">
                <option value="histogram">Histogram</option>
                <option value="kde">KDE</option>
                <option value="box">Box Plot</option>
                <option value="violin">Violin</option>
                <option value="ecdf">ECDF</option>
                <option value="qq">QQ Plot</option>
                <option value="cdf">CDF</option>
                <option value="frequency">Frequency</option>
                <option value="rug">Rug Plot</option>
              </select>
            </label>
            <button id="distPlotBtn" class="btn btn-primary btn-sm">Plot</button>
          </div>
          <div class="dist-export-group">
            <button class="btn btn-ghost btn-sm dist-export" data-format="csv">CSV</button>
            <button class="btn btn-ghost btn-sm dist-export" data-format="json">JSON</button>
          </div>
        </div>
      </div>
    `;
  }

  function renderDistDescriptiveTable(report) {
    const rows = report.columns.map(c => {
      const d = c.descriptive;
      return `
        <tr>
          <td class="dist-col-name">${esc(c.name)}</td>
          <td>${d.count}</td>
          <td>${fmt(d.mean)}</td>
          <td>${fmt(d.median)}</td>
          <td>${fmt(d.mode)}</td>
          <td>${fmt(d.min)}</td>
          <td>${fmt(d.max)}</td>
          <td>${fmt(d.range)}</td>
          <td>${fmt(d.variance)}</td>
          <td>${fmt(d.std)}</td>
          <td>${fmt(d.std_error)}</td>
          <td>${fmt(d.q1)}</td>
          <td>${fmt(d.q2)}</td>
          <td>${fmt(d.q3)}</td>
          <td>${fmt(d.iqr)}</td>
          <td>${fmt(d.cv)}%</td>
        </tr>
      `;
    }).join('');

    return `
      <div class="dist-section">
        <h2 class="report-title">Descriptive Statistics</h2>
        <div class="dist-table-wrap">
          <table class="report-table">
            <thead>
              <tr>
                <th>Column</th><th>Count</th><th>Mean</th><th>Median</th><th>Mode</th>
                <th>Min</th><th>Max</th><th>Range</th><th>Variance</th><th>Std Dev</th>
                <th>Std Error</th><th>Q1</th><th>Q2</th><th>Q3</th><th>IQR</th><th>CV</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderDistShapeSection(report) {
    const rows = report.columns.map(c => {
      const s = c.shape;
      const skewVal = s.skewness;
      const kurtVal = s.kurtosis;
      const shape = s.shape;

      let skewColor = 'var(--green)';
      if (skewVal !== null) {
        if (Math.abs(skewVal) > 1) skewColor = 'var(--red)';
        else if (Math.abs(skewVal) > 0.5) skewColor = 'var(--orange)';
      }

      let shapeBadge = 'dist-shape-symmetric';
      if (shape.includes('Right')) shapeBadge = 'dist-shape-right';
      else if (shape.includes('Left')) shapeBadge = 'dist-shape-left';
      else if (shape.includes('Peaked')) shapeBadge = 'dist-shape-peaked';
      else if (shape.includes('Flat')) shapeBadge = 'dist-shape-flat';

      return `
        <tr>
          <td class="dist-col-name">${esc(c.name)}</td>
          <td style="color:${skewColor};font-weight:700;font-family:var(--mono)">${skewVal !== null ? skewVal.toFixed(4) : '—'}</td>
          <td style="font-family:var(--mono)">${kurtVal !== null ? kurtVal.toFixed(4) : '—'}</td>
          <td><span class="dist-shape-badge ${shapeBadge}">${shape}</span></td>
        </tr>
      `;
    }).join('');

    return `
      <div class="dist-section">
        <h2 class="report-title">Distribution Shape Analysis</h2>
        <table class="report-table">
          <thead><tr><th>Column</th><th>Skewness</th><th>Kurtosis</th><th>Shape</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderDistNormalitySection(report) {
    const rows = [];
    report.columns.forEach(c => {
      c.normality.forEach(t => {
        const resultBadge = t.result === 'Normally Distributed' ? 'dist-normal-yes' : 'dist-normal-no';
        rows.push(`
          <tr>
            <td class="dist-col-name">${esc(c.name)}</td>
            <td>${esc(t.test)}</td>
            <td style="font-family:var(--mono)">${t.statistic !== null ? t.statistic.toFixed(4) : '—'}</td>
            <td style="font-family:var(--mono)">${t.p_value !== null ? t.p_value.toFixed(4) : '—'}</td>
            <td><span class="dist-normality-badge ${resultBadge}">${t.result}</span></td>
            <td class="dist-interpretation">${esc(t.interpretation)}</td>
          </tr>
        `);
      });
    });

    return `
      <div class="dist-section">
        <h2 class="report-title">Normality Tests</h2>
        <div class="dist-table-wrap">
          <table class="report-table">
            <thead><tr><th>Column</th><th>Test</th><th>Statistic</th><th>P-Value</th><th>Result</th><th>Interpretation</th></tr></thead>
            <tbody>${rows.join('')}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderDistPercentileSection(report) {
    const pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99];
    const headerRow = '<tr><th>Column</th>' + pcts.map(p => `<th>P${p}</th>`).join('') + '</tr>';
    const bodyRows = report.columns.map(c => {
      const cells = pcts.map(p => `<td style="font-family:var(--mono)">${fmt(c.percentiles['p' + p])}</td>`).join('');
      return `<tr><td class="dist-col-name">${esc(c.name)}</td>${cells}</tr>`;
    }).join('');

    return `
      <div class="dist-section">
        <h2 class="report-title">Percentile Analysis</h2>
        <div class="dist-table-wrap">
          <table class="report-table">
            <thead>${headerRow}</thead>
            <tbody>${bodyRows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderDistQualityScores(report) {
    const rows = report.columns.map(c => {
      const q = c.quality_score;
      let scoreClass = 'score-excellent';
      if (q.score < 50) scoreClass = 'score-poor';
      else if (q.score < 75) scoreClass = 'score-average';
      else if (q.score < 90) scoreClass = 'score-good';

      return `
        <tr>
          <td class="dist-col-name">${esc(c.name)}</td>
          <td>
            <div class="quality-score-bar"><div class="quality-score-fill ${scoreClass}" style="width:${q.score}%"></div></div>
            <span class="quality-score-text ${scoreClass}">${q.score}</span>
          </td>
          <td><span class="dist-shape-badge dist-q-${q.status.toLowerCase()}">${q.status}</span></td>
          <td>${c.outliers.count} (${c.outliers.percentage}%)</td>
        </tr>
      `;
    }).join('');

    return `
      <div class="dist-section">
        <h2 class="report-title">Distribution Quality Scores</h2>
        <table class="report-table">
          <thead><tr><th>Column</th><th>Score</th><th>Status</th><th>Outliers</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderDistFilters(report) {
    const opts = report.numeric_columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    return `
      <div class="dist-section">
        <h2 class="report-title">Interactive Filters</h2>
        <div class="dist-filter-bar">
          <label class="select-label">Column
            <select id="distFilterCol"><option value="">All</option>${opts}</select>
          </label>
          <label class="select-label">Distribution Type
            <select id="distFilterType">
              <option value="">All</option>
              <option value="normal">Normal Only</option>
              <option value="skewed">Skewed Only</option>
              <option value="outlier">With Outliers</option>
            </select>
          </label>
          <label class="select-label">Search
            <input type="text" id="distFilterSearch" class="dist-filter-input" placeholder="Search columns...">
          </label>
        </div>
        <div id="distFilterResults" class="dist-filter-results"></div>
      </div>
    `;
  }

  function renderDistComparison(report) {
    if (report.numeric_columns.length < 2) return '';
    const checkboxes = report.numeric_columns.map(c => `
      <label class="dist-checkbox-label">
        <input type="checkbox" class="dist-compare-check" value="${esc(c)}">
        <span>${esc(c)}</span>
      </label>
    `).join('');
    return `
      <div class="dist-section">
        <h2 class="report-title">Distribution Comparison</h2>
        <div class="dist-compare-controls">
          <div class="dist-compare-cols">
            <span class="select-label">Columns (select 2+)</span>
            <div class="dist-checkbox-group">${checkboxes}</div>
          </div>
          <label class="select-label">Type
            <select id="distCompareType">
              <option value="overlay_hist">Overlay Histogram</option>
              <option value="overlay_kde">Overlay KDE</option>
              <option value="box_compare">Boxplot Comparison</option>
              <option value="violin_compare">Violin Comparison</option>
              <option value="stats_compare">Stats Comparison</option>
            </select>
          </label>
          <button id="distCompareBtn" class="btn btn-primary btn-sm">Compare</button>
        </div>
        <div id="distCompareChart" class="dist-plotly-chart" style="min-height:400px"></div>
      </div>
    `;
  }

  function renderDistTransform(report) {
    if (!report.numeric_columns.length) return '';
    const opts = report.numeric_columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    return `
      <div class="dist-section">
        <h2 class="report-title">Transformation Preview</h2>
        <div class="dist-transform-controls">
          <label class="select-label">Column
            <select id="distTransformCol">${opts}</select>
          </label>
          <label class="select-label">Transform
            <select id="distTransformType">
              <option value="log">Log</option>
              <option value="sqrt">Square Root</option>
              <option value="boxcox">Box-Cox</option>
              <option value="yeojohnson">Yeo-Johnson</option>
              <option value="minmax">Min-Max Scaling</option>
              <option value="standardize">Standardization</option>
              <option value="robust">Robust Scaling</option>
            </select>
          </label>
          <button id="distTransformBtn" class="btn btn-primary btn-sm">Preview</button>
        </div>
        <div id="distTransformResult"></div>
      </div>
    `;
  }

  function renderDistInsights(insights) {
    const items = insights.map(i => `<div class="dist-insight-item">${esc(i)}</div>`).join('');
    return `
      <div class="dist-section">
        <h2 class="report-title">AI Distribution Insights</h2>
        <div class="dist-insights-list">${items}</div>
      </div>
    `;
  }

  function renderDistRecommendations(recs) {
    const priorityColors = {
      critical: 'var(--red)', high: 'var(--orange)',
      medium: 'var(--accent)', low: 'var(--green)',
    };
    const items = recs.map(r => `
      <div class="rec-card" style="border-left-color:${priorityColors[r.priority] || 'var(--text-faint)'}">
        <div class="rec-header">
          <span class="rec-priority" style="background:${priorityColors[r.priority] || 'var(--text-faint)'}">${r.priority}</span>
          <h3 class="rec-title">${esc(r.title)}</h3>
        </div>
        <p class="rec-description">${esc(r.description)}</p>
        ${r.affected_columns ? `<div class="rec-cols"><strong>Affected:</strong> ${r.affected_columns.map(c => `<span class="col-tag">${esc(c)}</span>`).join('')}</div>` : ''}
      </div>
    `).join('');
    return `
      <div class="dist-section">
        <h2 class="report-title">Recommendations</h2>
        <div class="recommendations-list">${items}</div>
      </div>
    `;
  }

  function renderDistExport() {
    return `
      <div class="dist-section">
        <h2 class="report-title">Export Options</h2>
        <div class="dist-export-options">
          <button class="btn btn-ghost btn-sm dist-export-all" data-format="csv">Export CSV</button>
          <button class="btn btn-ghost btn-sm dist-export-all" data-format="json">Export JSON</button>
        </div>
      </div>
    `;
  }

  // =========================================================================
  // Distribution UI initialization & interactions
  // =========================================================================
  function initDistributionUI(report) {
    if (!report || report.error) return;

    // Column + chart type selector
    const colSel = document.getElementById('distColumnSelect');
    const typeSel = document.getElementById('distChartTypeSelect');
    const plotBtn = document.getElementById('distPlotBtn');

    if (plotBtn && colSel && typeSel) {
      plotBtn.addEventListener('click', () => renderDistChart(colSel.value, typeSel.value));
      // Auto-render first column
      if (report.numeric_columns.length) {
        renderDistChart(report.numeric_columns[0], 'histogram');
      }
    }

    // Export buttons (inline)
    document.querySelectorAll('.dist-export').forEach(btn => {
      btn.addEventListener('click', () => exportDistribution(btn.dataset.format));
    });

    // Export all buttons
    document.querySelectorAll('.dist-export-all').forEach(btn => {
      btn.addEventListener('click', () => exportDistribution(btn.dataset.format));
    });

    // Filter controls
    bindDistFilters(report);

    // Comparison
    const compareBtn = document.getElementById('distCompareBtn');
    if (compareBtn) {
      compareBtn.addEventListener('click', () => {
        const type = document.getElementById('distCompareType');
        const cols = Array.from(document.querySelectorAll('.dist-compare-check:checked')).map(cb => cb.value);
        if (cols.length < 2) { showToast('Select at least 2 columns', 'error'); return; }
        renderDistComparisonChart(cols, type.value);
      });
    }

    // Transform
    const transformBtn = document.getElementById('distTransformBtn');
    if (transformBtn) {
      transformBtn.addEventListener('click', () => {
        const col = document.getElementById('distTransformCol').value;
        const transform = document.getElementById('distTransformType').value;
        renderDistTransformPreview(col, transform);
      });
    }
  }

  async function renderDistChart(col, chartType) {
    const plotDiv = document.getElementById('distMainChart');
    if (!plotDiv) return;
    plotDiv.innerHTML = '<div class="chart-placeholder"><div class="loader-spinner"></div></div>';

    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/distribution/chart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ column: col, chart_type: chartType }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error);

      const spec = data.spec;
      plotDiv.innerHTML = '';
      Plotly.newPlot('distMainChart', spec.data, spec.layout, {
        responsive: true, displayModeBar: true, displaylogo: false,
      });
    } catch (e) {
      plotDiv.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
    }
  }

  async function renderDistComparisonChart(cols, chartType) {
    const plotDiv = document.getElementById('distCompareChart');
    if (!plotDiv) return;
    plotDiv.innerHTML = '<div class="chart-placeholder"><div class="loader-spinner"></div></div>';

    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/distribution/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ columns: cols, chart_type: chartType }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      const result = data.result;
      if (result.error) throw new Error(result.error);

      plotDiv.innerHTML = '';
      Plotly.newPlot('distCompareChart', result.data, result.layout, {
        responsive: true, displayModeBar: true, displaylogo: false,
      });
    } catch (e) {
      plotDiv.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
    }
  }

  async function renderDistTransformPreview(col, transform) {
    const resultDiv = document.getElementById('distTransformResult');
    if (!resultDiv) return;
    resultDiv.innerHTML = '<div class="chart-placeholder"><div class="loader-spinner"></div></div>';

    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/distribution/transform`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ column: col, transform }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error);
      if (data.error) throw new Error(data.error);

      let html = '<div class="dist-transform-result">';
      html += `<div class="dist-transform-info">
        <span>Original Skew: <strong>${data.original_skew}</strong></span>
        <span>Transformed Skew: <strong>${data.transformed_skew}</strong></span>
        <span>Transform: <strong>${esc(data.label)}</strong></span>
      </div>`;
      html += '<div id="distTransformPlot" class="dist-plotly-chart" style="min-height:400px"></div>';
      html += '</div>';
      resultDiv.innerHTML = html;

      requestAnimationFrame(() => {
        const spec = data.spec;
        Plotly.newPlot('distTransformPlot', spec.data, spec.layout, {
          responsive: true, displayModeBar: true, displaylogo: false,
        });
      });
    } catch (e) {
      resultDiv.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
    }
  }

  function bindDistFilters(report) {
    const colFilter = document.getElementById('distFilterCol');
    const typeFilter = document.getElementById('distFilterType');
    const searchFilter = document.getElementById('distFilterSearch');
    const resultsDiv = document.getElementById('distFilterResults');

    function applyFilters() {
      const colVal = colFilter ? colFilter.value : '';
      const typeVal = typeFilter ? typeFilter.value : '';
      const searchVal = searchFilter ? searchFilter.value.toLowerCase() : '';

      let filtered = report.columns;

      if (colVal) filtered = filtered.filter(c => c.name === colVal);
      if (searchVal) filtered = filtered.filter(c => c.name.toLowerCase().includes(searchVal));
      if (typeVal === 'normal') filtered = filtered.filter(c => c.normality.every(t => t.result === 'Normally Distributed'));
      if (typeVal === 'skewed') filtered = filtered.filter(c => c.shape.shape.includes('Skewed'));
      if (typeVal === 'outlier') filtered = filtered.filter(c => c.outliers.count > 0);

      if (resultsDiv) {
        if (filtered.length === 0) {
          resultsDiv.innerHTML = '<p class="text-dim" style="padding:12px;">No columns match the filter criteria.</p>';
        } else {
          resultsDiv.innerHTML = '<div class="dist-filter-list">' + filtered.map(c => `
            <div class="dist-filter-item">
              <span class="dist-filter-name">${esc(c.name)}</span>
              <span class="dist-shape-badge dist-shape-${c.shape.shape.includes('Right') ? 'right' : c.shape.shape.includes('Left') ? 'left' : 'symmetric'}">${c.shape.shape}</span>
              <span class="dist-normality-badge ${c.normality.every(t => t.result === 'Normally Distributed') ? 'dist-normal-yes' : 'dist-normal-no'}">${c.normality.length ? c.normality[0].result : '—'}</span>
              <span style="font-family:var(--mono);font-size:.78rem">Q: ${c.quality_score.score}</span>
            </div>
          `).join('') + '</div>';
        }
      }
    }

    if (colFilter) colFilter.addEventListener('change', applyFilters);
    if (typeFilter) typeFilter.addEventListener('change', applyFilters);
    if (searchFilter) searchFilter.addEventListener('input', applyFilters);

    // Initial render
    applyFilters();
  }

  function exportDistribution(format) {
    if (!state.distributionReport || !state.distributionReport.columns) return;

    fetch(`${API}/api/session/${state.sessionId}/distribution/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, columns: state.distributionReport.columns }),
    })
      .then(r => r.text().then(text => ({ text, ext: format === 'json' ? 'json' : 'csv' })))
      .then(({ text, ext }) => {
        const blob = new Blob([text], { type: ext === 'json' ? 'application/json' : 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `distribution.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showToast(`Exported distribution as ${ext.toUpperCase()}`, 'success');
      })
      .catch(e => showToast('Export failed: ' + e.message, 'error'));
  }

  // =========================================================================
  // Downloads
  // =========================================================================
  function bindDownloads() {
    $('#downloadCsv').addEventListener('click', () => download('csv'));
    $('#downloadJson').addEventListener('click', () => download('json'));
  }

  function download(format) {
    if (!state.sessionId) return;
    const url = `${API}/api/session/${state.sessionId}/download?format=${format}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast(`Downloading ${format.toUpperCase()}…`, 'info');
  }

  // =========================================================================
  // Share
  // =========================================================================
  function bindShare() {
    $('#shareBtn').addEventListener('click', async () => {
      const url = window.location.href;
      try {
        await navigator.clipboard.writeText(url);
        showToast('Shareable link copied to clipboard!', 'success');
      } catch {
        // Fallback.
        window.prompt('Copy this link to share:', url);
      }
    });
  }

  // =========================================================================
  // Sidebar toggle (inner sidebar for preview)
  // =========================================================================
  function bindSidebar() {
    const sidebarToggleInner = $('#sidebarToggleInner');
    if (!sidebarToggleInner) return;
    sidebarToggleInner.addEventListener('click', () => {
      const sidebar = $('#sidebar');
      if (sidebar) sidebar.style.display = sidebar.style.display === 'none' ? '' : 'none';
    });
  }

  // =========================================================================
  // EDA Report
  // =========================================================================
  function bindEdaReport() {
    const btnGenerate = $('#btnGenerateEda');
    const exportBar = $('#edaExportBar');

    if (btnGenerate) {
      btnGenerate.addEventListener('click', generateEdaReport);
    }

    if (exportBar) {
      exportBar.querySelectorAll('[data-export]').forEach((btn) => {
        btn.addEventListener('click', () => exportEdaReport(btn.dataset.export));
      });
    }
  }

  async function generateEdaReport() {
    if (!state.sessionId) return;
    showLoader('Generating EDA report…');
    try {
      const reportType = $('#edaReportType')?.value || 'full';
      const customTitle = $('#edaReportTitle')?.value || '';
      const customAuthor = $('#edaReportAuthor')?.value || '';

      const res = await fetch(`${API}/api/session/${state.sessionId}/eda-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_type: reportType, custom_title: customTitle, custom_author: customAuthor }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Failed to generate EDA report');
      }
      const report = await res.json();
      state.edaReport = report;
      renderEdaReport(report);
      $('#edaExportBar')?.removeAttribute('hidden');
      showToast('EDA report generated successfully', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  function renderEdaReport(report) {
    const container = $('#edaReportContainer');
    if (!container) return;

    const sections = [];
    const ov = report.dataset_overview || {};
    const q = report.quality || {};
    const hs = q.health_score || {};
    const corr = report.correlation || {};
    const dist = report.distribution || {};
    const out = report.outliers || {};
    const ml = report.ml_readiness || {};
    const biz = report.business_story || {};
    const insights = report.insights || [];
    const colIntel = report.column_intelligence || [];
    const stats = report.descriptive_stats || {};

    // Executive summary
    sections.push(`
      <div class="eda-section" id="eda-exec">
        <h2>Executive Summary</h2>
        <div class="eda-stat-row">
          <div class="eda-stat-card"><div class="eda-stat-label">Rows</div><div class="eda-stat-value">${p_n(ov.rows || 0)}</div></div>
          <div class="eda-stat-card"><div class="eda-stat-label">Columns</div><div class="eda-stat-value">${ov.columns || 0}</div></div>
          <div class="eda-stat-card"><div class="eda-stat-label">Memory</div><div class="eda-stat-value">${ov.memory_mb || 0} MB</div></div>
          <div class="eda-stat-card"><div class="eda-stat-label">Quality</div><div class="eda-stat-value eda-score-${hs.score >= 80 ? 'good' : hs.score >= 60 ? 'fair' : 'poor'}">${hs.score || 0}/100</div></div>
          <div class="eda-stat-card"><div class="eda-stat-label">Missing</div><div class="eda-stat-value">${ov.missing_pct || 0}%</div></div>
        </div>
        ${biz.situation ? `<div class="eda-insight-box"><h3>Situation</h3><p>${esc(biz.situation)}</p></div>` : ''}
        ${insights.length ? `<div class="eda-insight-box"><h3>Key Insights</h3><ul>${insights.slice(0, 6).map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : ''}
      </div>
    `);

    // Quality breakdown
    const breakdown = hs.breakdown || {};
    const breakdownHtml = Object.entries(breakdown).map(([k, v]) => `
      <div class="eda-progress-item">
        <div class="eda-progress-label"><span>${esc(k)}</span><span>${v}</span></div>
        <div class="eda-progress-bar"><div class="eda-progress-fill eda-score-${v >= 80 ? 'good' : v >= 60 ? 'fair' : 'poor'}" style="width:${v}%"></div></div>
      </div>
    `).join('');

    sections.push(`
      <div class="eda-section" id="eda-quality">
        <h2>Data Quality</h2>
        <div class="eda-quality-score">
          <div class="eda-score-circle eda-score-${hs.score >= 80 ? 'good' : hs.score >= 60 ? 'fair' : 'poor'}">${hs.score || 0}</div>
          <div><div class="eda-score-label">Overall Health</div><span class="eda-badge eda-badge-${hs.score >= 80 ? 'green' : hs.score >= 60 ? 'blue' : 'red'}">${hs.status || ''}</span></div>
        </div>
        <div class="eda-progress-list">${breakdownHtml}</div>
      </div>
    `);

    // Correlation
    const corrPairs = corr.pairs || [];
    if (corrPairs.length) {
      const corrRows = corrPairs.slice(0, 15).map(p => `
        <tr>
          <td><strong>${esc(p.feature_a)}</strong></td>
          <td><strong>${esc(p.feature_b)}</strong></td>
          <td class="eda-corr-val eda-corr-${p.value > 0 ? 'pos' : 'neg'}">${p.value.toFixed(4)}</td>
          <td><span class="eda-badge eda-badge-${p.strength === 'strong' ? 'green' : p.strength === 'moderate' ? 'blue' : 'gray'}">${p.strength}</span></td>
        </tr>
      `).join('');

      sections.push(`
        <div class="eda-section" id="eda-corr">
          <h2>Correlation Analysis</h2>
          <div class="eda-table-wrap">
            <table class="eda-table">
              <thead><tr><th>Feature A</th><th>Feature B</th><th>Correlation</th><th>Strength</th></tr></thead>
              <tbody>${corrRows}</tbody>
            </table>
          </div>
        </div>
      `);
    }

    // Distribution
    const distCols = dist.columns || [];
    if (distCols.length) {
      const distRows = distCols.map(c => {
        const shape = c.shape || {};
        const qs = c.quality_score || {};
        return `
          <tr>
            <td><strong>${esc(c.name)}</strong></td>
            <td class="eda-corr-val ${Math.abs(shape.skewness || 0) < 0.5 ? 'eda-score-good' : 'eda-score-fair'}">${(shape.skewness || 0).toFixed(4)}</td>
            <td>${(shape.kurtosis || 0).toFixed(4)}</td>
            <td><span class="eda-badge eda-badge-blue">${shape.shape || ''}</span></td>
            <td>${qs.score || 0} — ${esc(qs.status || '')}</td>
          </tr>
        `;
      }).join('');

      sections.push(`
        <div class="eda-section" id="eda-dist">
          <h2>Distribution Analysis</h2>
          <div class="eda-table-wrap">
            <table class="eda-table">
              <thead><tr><th>Column</th><th>Skewness</th><th>Kurtosis</th><th>Shape</th><th>Quality</th></tr></thead>
              <tbody>${distRows}</tbody>
            </table>
          </div>
        </div>
      `);
    }

    // Outliers
    const outCols = out.columns || [];
    if (outCols.length) {
      const outRows = outCols.map(c => `
        <tr>
          <td><strong>${esc(c.name)}</strong></td>
          <td>${p_n(c.iqr_outliers)}</td>
          <td>${p_n(c.zscore_outliers)}</td>
          <td>${c.percentage}%</td>
          <td><span class="eda-badge eda-badge-${c.severity === 'high' ? 'red' : c.severity === 'medium' ? 'yellow' : 'green'}">${c.severity}</span></td>
        </tr>
      `).join('');

      sections.push(`
        <div class="eda-section" id="eda-outliers">
          <h2>Outlier Analysis</h2>
          <div class="eda-stat-row"><div class="eda-stat-card"><div class="eda-stat-label">Total Outliers</div><div class="eda-stat-value eda-score-poor">${p_n(out.total_outliers || 0)}</div></div></div>
          <div class="eda-table-wrap">
            <table class="eda-table">
              <thead><tr><th>Column</th><th>IQR Outliers</th><th>Z-Score</th><th>%</th><th>Severity</th></tr></thead>
              <tbody>${outRows}</tbody>
            </table>
          </div>
        </div>
      `);
    }

    // ML Readiness
    if (ml.score !== undefined) {
      sections.push(`
        <div class="eda-section" id="eda-ml">
          <h2>ML Readiness</h2>
          <div class="eda-stat-row">
            <div class="eda-stat-card"><div class="eda-stat-label">Score</div><div class="eda-stat-value">${ml.score}</div></div>
            <div class="eda-stat-card"><div class="eda-stat-label">Numeric</div><div class="eda-stat-value">${ml.numeric_features || 0}</div></div>
            <div class="eda-stat-card"><div class="eda-stat-label">Categorical</div><div class="eda-stat-value">${ml.categorical_features || 0}</div></div>
            <div class="eda-stat-card"><div class="eda-stat-label">Targets</div><div class="eda-stat-value">${(ml.target_candidates || []).length}</div></div>
          </div>
          ${ml.encoding_needed ? '<span class="eda-badge eda-badge-yellow">Encoding Needed</span> ' : ''}
          ${ml.scaling_needed ? '<span class="eda-badge eda-badge-blue">Scaling Needed</span>' : ''}
        </div>
      `);
    }

    // Business Story
    if (biz.situation) {
      sections.push(`
        <div class="eda-section" id="eda-biz">
          <h2>Business Story</h2>
          <div class="eda-insight-box"><h3>Situation</h3><p>${esc(biz.situation)}</p></div>
          ${biz.observations?.length ? `<div class="eda-insight-box"><h3>Observations</h3><ul>${biz.observations.map(o => `<li>${esc(o)}</li>`).join('')}</ul></div>` : ''}
          ${biz.risks?.length ? `<div class="eda-insight-box eda-risk"><h3>Risks</h3><ul>${biz.risks.map(r => `<li>${esc(r)}</li>`).join('')}</ul></div>` : ''}
          ${biz.opportunities?.length ? `<div class="eda-insight-box eda-opp"><h3>Opportunities</h3><ul>${biz.opportunities.map(o => `<li>${esc(o)}</li>`).join('')}</ul></div>` : ''}
          ${biz.next_steps?.length ? `<div class="eda-insight-box"><h3>Next Steps</h3><ol>${biz.next_steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol></div>` : ''}
        </div>
      `);
    }

    container.innerHTML = `
      <div class="eda-report-rendered">
        <div class="eda-report-header">
          <h1>${esc(report.branding?.title || 'EDA Report')}</h1>
          <div class="eda-report-meta">Author: ${esc(report.branding?.author || 'Data Drop')} &middot; Generated: ${(report.generated_at || '').slice(0, 10)}</div>
        </div>
        ${sections.join('')}
      </div>
    `;
  }

  async function exportEdaReport(format) {
    if (!state.edaReport) {
      showToast('Generate a report first', 'error');
      return;
    }
    showLoader(`Exporting ${format.toUpperCase()}…`);
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/eda-report/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, report_data: state.edaReport }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Export failed');
      }
      const blob = await res.blob();
      const ext = { html: 'html', json: 'json', markdown: 'md', excel: 'xlsx' }[format] || format;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${state.filename?.replace(/\.[^.]+$/, '') || 'eda_report'}_eda.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast(`Exported ${format.toUpperCase()} successfully`, 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  // =========================================================================
  // AI Insights Engine
  // =========================================================================
  function bindAiInsights() {
    const btnGenerate = $('#btnGenerateInsights');
    const btnRefresh = $('#btnRefreshInsights');
    const searchInput = $('#aiInsightSearch');
    const exportBar = $('#aiExportBar');

    if (btnGenerate) {
      btnGenerate.addEventListener('click', generateAiInsights);
    }
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => generateAiInsights(true));
    }
    if (searchInput) {
      searchInput.addEventListener('input', filterAiInsights);
    }
    if (exportBar) {
      exportBar.querySelectorAll('[data-export]').forEach((btn) => {
        btn.addEventListener('click', () => exportAiInsights(btn.dataset.export));
      });
    }
    // Priority filter chips
    const chipContainer = $('#aiFilterChips');
    if (chipContainer) {
      chipContainer.querySelectorAll('.ai-chip').forEach((chip) => {
        chip.addEventListener('click', () => {
          chipContainer.querySelectorAll('.ai-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          filterAiInsights();
        });
      });
    }
    // Category filter chips
    const catContainer = $('#aiFilterCategories');
    if (catContainer) {
      catContainer.querySelectorAll('.ai-cat-chip').forEach((chip) => {
        chip.addEventListener('click', () => {
          catContainer.querySelectorAll('.ai-cat-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          filterAiInsights();
        });
      });
    }
  }

  async function generateAiInsights(forceRefresh = false) {
    if (!state.sessionId) return;
    showLoader('AI is analyzing your dataset…');
    const btn = $('#btnGenerateInsights');
    if (btn) btn.disabled = true;
    try {
      const context = $('#aiInsightContext')?.value || '';
      const res = await fetch(`${API}/api/session/${state.sessionId}/ai-insights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_refresh: forceRefresh, context }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Failed to generate insights');
      }
      const data = await res.json();
      state.aiInsights = data;
      renderAiInsights(data);
      $('#aiFilterBar')?.removeAttribute('hidden');
      $('#aiExportBar')?.removeAttribute('hidden');
      $('#btnRefreshInsights')?.removeAttribute('hidden');
      showToast('AI insights generated successfully', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
      if (btn) btn.disabled = false;
    }
  }

  function renderAiInsights(data) {
    const container = $('#aiInsightsContainer');
    if (!container) return;

    let html = '';

    // Dataset understanding
    const du = data.dataset_understanding || {};
    if (du.purpose) {
      html += `
        <div class="ai-section ai-understanding" data-insight-category="business">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
            <h2>Dataset Understanding</h2>
          </div>
          <div class="ai-understanding-content">
            <p class="ai-understanding-purpose">${esc(du.purpose)}</p>
            <div class="ai-understanding-meta">
              <span class="ai-badge ai-badge-blue">Domain: ${esc(du.domain || 'General')}</span>
              <span class="ai-badge ai-badge-green">Confidence: ${du.confidence || 0}%</span>
            </div>
            ${du.key_columns?.length ? `<div class="ai-key-cols"><strong>Key Columns:</strong> ${du.key_columns.map(c => `<span class="ai-tag">${esc(c)}</span>`).join(' ')}</div>` : ''}
            ${du.use_cases?.length ? `<div class="ai-use-cases"><strong>Use Cases:</strong> <ul>${du.use_cases.map(u => `<li>${esc(u)}</li>`).join('')}</ul></div>` : ''}
          </div>
        </div>`;
    }

    // Executive summary
    const es = data.executive_summary || {};
    if (es.situation) {
      html += `
        <div class="ai-section ai-exec-summary" data-insight-category="business">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <h2>Executive Summary</h2>
          </div>
          <div class="ai-exec-content">
            <p class="ai-situation">${esc(es.situation)}</p>
            ${es.key_findings?.length ? `<div class="ai-findings"><h3>Key Findings</h3><ul>${es.key_findings.filter(Boolean).map(f => `<li>${esc(f)}</li>`).join('')}</ul></div>` : ''}
            ${es.risks?.length ? `<div class="ai-risks"><h3>Risks</h3><ul>${es.risks.filter(Boolean).map(r => `<li class="ai-risk-item">${esc(r)}</li>`).join('')}</ul></div>` : ''}
            ${es.opportunities?.length ? `<div class="ai-opps"><h3>Opportunities</h3><ul>${es.opportunities.filter(Boolean).map(o => `<li class="ai-opp-item">${esc(o)}</li>`).join('')}</ul></div>` : ''}
            ${es.recommendations?.length ? `<div class="ai-recs"><h3>Recommendations</h3><ol>${es.recommendations.filter(Boolean).map(r => `<li>${esc(r)}</li>`).join('')}</ol></div>` : ''}
          </div>
        </div>`;
    }

    // Data quality
    const dq = data.data_quality_assessment || {};
    if (dq.score !== undefined) {
      const scoreColor = dq.score >= 80 ? 'good' : dq.score >= 60 ? 'fair' : 'poor';
      html += `
        <div class="ai-section ai-quality" data-insight-category="quality">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            <h2>Data Quality Assessment</h2>
            <span class="ai-score ai-score-${scoreColor}">${dq.score}/100</span>
          </div>
          <div class="ai-quality-content">
            <span class="ai-badge ai-badge-${scoreColor === 'good' ? 'green' : scoreColor === 'fair' ? 'yellow' : 'red'}">${esc(dq.status || '')}</span>
            ${dq.issues?.length ? `<div class="ai-issues"><h3>Issues</h3><ul>${dq.issues.map(i => `<li class="ai-risk-item">${esc(i)}</li>`).join('')}</ul></div>` : ''}
            ${dq.treatment_recommendations?.length ? `<div class="ai-treatment"><h3>Recommended Treatment</h3><ul>${dq.treatment_recommendations.map(r => `<li>${esc(r)}</li>`).join('')}</ul></div>` : ''}
          </div>
        </div>`;
    }

    // Insights
    const insights = data.insights || [];
    if (insights.length) {
      html += `
        <div class="ai-section ai-insights-list">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 017 7c0 3-2 5-4 6v2H9v-2c-2-1-4-3-4-6a7 7 0 017-7z"/></svg>
            <h2>Insights (${insights.length})</h2>
          </div>
          <div class="ai-insight-cards" id="aiInsightCards">
            ${insights.map(ins => renderInsightCard(ins)).join('')}
          </div>
        </div>`;
    }

    // KPIs
    const kpis = data.kpis || [];
    if (kpis.length) {
      html += `
        <div class="ai-section ai-kpis" data-insight-category="kpi">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
            <h2>Key Performance Indicators</h2>
          </div>
          <div class="ai-kpi-grid">
            ${kpis.map(kpi => {
              const trendIcon = { increasing: '📈', decreasing: '📉', stable: '➡️', volatile: '📊' }[kpi.trend] || '📊';
              const statusClass = { good: 'green', warning: 'yellow', critical: 'red' }[kpi.status] || 'blue';
              return `
                <div class="ai-kpi-card">
                  <div class="ai-kpi-name">${esc(kpi.name)}</div>
                  <div class="ai-kpi-value">${esc(String(kpi.value))} ${trendIcon}</div>
                  <div class="ai-kpi-desc">${esc(kpi.description)}</div>
                  <span class="ai-badge ai-badge-${statusClass}">${esc(kpi.status)}</span>
                </div>`;
            }).join('')}
          </div>
        </div>`;
    }

    // Risks
    const risks = data.risks || [];
    if (risks.length) {
      html += `
        <div class="ai-section ai-risks-section" data-insight-category="risk">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <h2>Risk Assessment (${risks.length})</h2>
          </div>
          <div class="ai-risk-cards">
            ${risks.map(risk => {
              const sevClass = { critical: 'red', high: 'orange', medium: 'yellow', low: 'green' }[risk.severity] || 'blue';
              return `
                <div class="ai-risk-card">
                  <div class="ai-risk-header">
                    <span class="ai-badge ai-badge-${sevClass}">${esc(risk.severity)}</span>
                    <strong>${esc(risk.title)}</strong>
                  </div>
                  <p class="ai-risk-desc">${esc(risk.description)}</p>
                  ${risk.impact ? `<div class="ai-risk-impact"><strong>Impact:</strong> ${esc(risk.impact)}</div>` : ''}
                  ${risk.mitigation ? `<div class="ai-risk-mitigation"><strong>Mitigation:</strong> ${esc(risk.mitigation)}</div>` : ''}
                </div>`;
            }).join('')}
          </div>
        </div>`;
    }

    // ML Recommendations
    const ml = data.ml_recommendations || {};
    if (ml.target_candidates?.length || ml.recommended_tasks?.length) {
      html += `
        <div class="ai-section ai-ml" data-insight-category="ml">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            <h2>Machine Learning Readiness</h2>
          </div>
          <div class="ai-ml-content">
            ${ml.target_candidates?.length ? `<div class="ai-ml-targets"><strong>Target Candidates:</strong> ${ml.target_candidates.map(t => `<span class="ai-tag">${esc(t)}</span>`).join(' ')}</div>` : ''}
            ${ml.recommended_tasks?.length ? `<div class="ai-ml-tasks"><strong>Recommended Tasks:</strong> ${ml.recommended_tasks.map(t => `<span class="ai-badge ai-badge-blue">${esc(t)}</span>`).join(' ')}</div>` : ''}
            ${ml.algorithms?.length ? `<div class="ai-ml-algo"><strong>Suggested Algorithms:</strong> ${ml.algorithms.map(a => `<span class="ai-tag">${esc(a)}</span>`).join(' ')}</div>` : ''}
            ${ml.feature_engineering?.length ? `<div class="ai-ml-fe"><strong>Feature Engineering:</strong><ul>${ml.feature_engineering.map(f => `<li>${esc(f)}</li>`).join('')}</ul></div>` : ''}
          </div>
        </div>`;
    }

    // Forecast suggestions
    const fc = data.forecast_suggestions || [];
    if (fc.length) {
      html += `
        <div class="ai-section ai-forecast" data-insight-category="business">
          <div class="ai-section-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            <h2>Forecasting Suggestions</h2>
          </div>
          <div class="ai-forecast-list">
            ${fc.map(f => `
              <div class="ai-forecast-item">
                <strong>${esc(f.column)}</strong> → ${esc(f.metric)} via <span class="ai-badge ai-badge-blue">${esc(f.method)}</span>
                <div class="ai-forecast-reason">${esc(f.reason)}</div>
              </div>
            `).join('')}
          </div>
        </div>`;
    }

    // Fallback notice
    if (data.fallback_mode) {
      html += `
        <div class="ai-section ai-fallback-notice" data-insight-category="quality">
          <div class="ai-notice ai-notice-warning">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>Insights generated from statistical analysis (AI unavailable). Configure AI_STUDIO_API_KEY for enhanced insights.</span>
          </div>
        </div>`;
    }

    container.innerHTML = html || '<div class="report-placeholder"><p>No insights generated.</p></div>';
  }

  function renderInsightCard(ins) {
    const priorityClass = { critical: 'red', high: 'orange', medium: 'yellow', low: 'green' }[ins.priority] || 'blue';
    const categoryIcons = {
      business: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>',
      quality: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
      correlation: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="3" height="3"/><rect x="14" y="14" width="3" height="3"/></svg>',
      outlier: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>',
      distribution: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 20h18M5 20V10M9 20V4M13 20V8M17 20V6M21 20V12"/></svg>',
      kpi: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
      ml: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/></svg>',
      risk: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    };
    const icon = categoryIcons[ins.category] || categoryIcons.business;

    return `
      <div class="ai-insight-card" data-priority="${ins.priority}" data-category="${ins.category}" data-id="${esc(ins.id)}">
        <div class="ai-card-header">
          <span class="ai-card-category">${icon} ${esc(ins.category)}</span>
          <span class="ai-badge ai-badge-${priorityClass}">${esc(ins.priority)}</span>
          <span class="ai-impact-score">Impact: ${ins.impact_score}/10</span>
        </div>
        <h3 class="ai-card-title">${esc(ins.title)}</h3>
        <p class="ai-card-detail">${esc(ins.detail)}</p>
        ${ins.evidence ? `<div class="ai-card-evidence"><strong>Evidence:</strong> ${esc(ins.evidence)}</div>` : ''}
        ${ins.action ? `<div class="ai-card-action"><strong>Action:</strong> ${esc(ins.action)}</div>` : ''}
        <div class="ai-card-actions">
          <button class="ai-card-btn" onclick="navigator.clipboard.writeText('${esc(ins.detail).replace(/'/g, "\\'")}')">Copy</button>
        </div>
      </div>`;
  }

  function filterAiInsights() {
    const search = ($('#aiInsightSearch')?.value || '').toLowerCase();
    const priorityFilter = $('.ai-chip.active')?.dataset?.filter || 'all';
    const categoryFilter = $('.ai-cat-chip.active')?.dataset?.cat || 'all';

    const cards = $$('#aiInsightCards .ai-insight-card');
    cards.forEach((card) => {
      const text = card.textContent.toLowerCase();
      const priority = card.dataset.priority;
      const category = card.dataset.category;

      let show = true;
      if (search && !text.includes(search)) show = false;
      if (priorityFilter !== 'all' && priority !== priorityFilter) show = false;
      if (categoryFilter !== 'all' && category !== categoryFilter) show = false;

      card.style.display = show ? '' : 'none';
    });
  }

  async function exportAiInsights(format) {
    if (!state.aiInsights) {
      showToast('Generate insights first', 'error');
      return;
    }
    showLoader(`Exporting ${format.toUpperCase()}…`);
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/ai-insights/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, report_data: state.aiInsights }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Export failed');
      }
      const blob = await res.blob();
      const ext = { markdown: 'md', html: 'html', json: 'json', csv: 'csv' }[format] || format;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${state.filename?.replace(/\.[^.]+$/, '') || 'ai_insights'}_insights.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast(`Exported ${format.toUpperCase()} successfully`, 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  // =========================================================================
  // Ask Your Data (NLQ)
  // =========================================================================
  function bindAskData() {
    const btn = $('#btnAsk');
    const input = $('#askInput');
    if (btn) btn.addEventListener('click', askQuestion);
    if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') askQuestion(); });
  }

  async function askQuestion() {
    if (!state.sessionId) return;
    const question = $('#askInput')?.value?.trim();
    if (!question) return;
    showLoader('AI is thinking…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Query failed');
      renderAskResult(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  function renderAskResult(data) {
    const container = $('#askResultContainer');
    if (!container) return;
    let html = `<div class="ask-answer">`;
    html += `<div class="ask-question-display">"${esc(data.question)}"</div>`;
    if (data.explanation) html += `<div class="ask-explanation">${esc(data.explanation)}</div>`;
    if (data.code) html += `<pre class="ask-code"><code>${esc(data.code)}</code></pre>`;
    if (data.output) {
      const out = data.output;
      if (out.type === 'dataframe' && out.rows) {
        html += `<div class="ask-table-wrap"><table class="ask-table"><thead><tr>${out.columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${out.rows.map(r => `<tr>${out.columns.map(c => `<td>${esc(String(r[c] ?? ''))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
        if (out.shape) html += `<div class="ask-meta">${out.shape[0]} rows × ${out.shape[1]} columns</div>`;
      } else if (out.type === 'number') {
        html += `<div class="ask-number">${fmt(out.value)}</div>`;
      } else if (out.type === 'text') {
        html += `<div class="ask-text">${esc(out.value)}</div>`;
      } else if (out.type === 'dict' || out.type === 'series') {
        html += `<pre class="ask-json"><code>${esc(JSON.stringify(out.data, null, 2))}</code></pre>`;
      }
    }
    if (data.chart_spec && typeof Plotly !== 'undefined') {
      html += `<div id="askChart" class="ask-chart"></div>`;
    }
    if (data.error) html += `<div class="ask-error">Error: ${esc(data.error)}</div>`;
    html += `</div>`;
    container.innerHTML = html;
    if (data.chart_spec && typeof Plotly !== 'undefined') {
      Plotly.newPlot('askChart', data.chart_spec.data || [], data.chart_spec.layout || {}, { responsive: true, displayModeBar: false });
    }
  }

  // =========================================================================
  // Feature Engineering
  // =========================================================================
  function bindFeatureEngineering() {
    $('#btnFeEncode')?.addEventListener('click', () => runFeatureOp('encode'));
    $('#btnFeScale')?.addEventListener('click', () => runFeatureOp('scale'));
    $('#btnFeTransform')?.addEventListener('click', () => runFeatureOp('transform'));
    $('#btnFeCreate')?.addEventListener('click', () => runFeatureOp('create'));
  }

  function populateFeatureSelects() {
    if (!state.profile) return;
    const cols = state.profile.columns;
    const numCols = cols.filter(c => c.type === 'numeric').map(c => c.name);
    const allCols = cols.map(c => c.name);
    ['feEncodeColumns', 'feScaleColumns', 'feTransformColumns', 'feCreateColumns'].forEach(id => {
      const sel = $(`#${id}`);
      if (!sel) return;
      const options = (id === 'feScaleColumns' || id === 'feTransformColumns') ? numCols : allCols;
      sel.innerHTML = options.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    });
    // Stats selects
    ['statsColumn', 'statsNormalityCol', 'statsColA', 'statsColB'].forEach(id => {
      const sel = $(`#${id}`);
      if (!sel) return;
      sel.innerHTML = numCols.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    });
  }

  async function runFeatureOp(type) {
    if (!state.sessionId) return;
    showLoader('Applying feature engineering…');
    try {
      let endpoint, body;
      if (type === 'encode') {
        endpoint = '/feature-engineering/encode';
        body = { method: $('#feEncodeMethod').value, columns: getSelectedValues('#feEncodeColumns') };
      } else if (type === 'scale') {
        endpoint = '/feature-engineering/scale';
        body = { method: $('#feScaleMethod').value, columns: getSelectedValues('#feScaleColumns') };
      } else if (type === 'transform') {
        endpoint = '/feature-engineering/transform';
        body = { method: $('#feTransformMethod').value, columns: getSelectedValues('#feTransformColumns') };
      } else {
        endpoint = '/feature-engineering/create';
        body = { operation: $('#feCreateOp').value, columns: getSelectedValues('#feCreateColumns') };
      }
      const res = await fetch(`${API}/api/session/${state.sessionId}${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Operation failed');
      state.profile = data.profile;
      state.preview = data.preview;
      state.history = data.history || [];
      renderProfile();
      renderPreview();
      populateFeatureSelects();
      showToast(`${type} operation completed`, 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      hideLoader();
    }
  }

  function getSelectedValues(sel) {
    const el = $(sel);
    if (!el) return [];
    return Array.from(el.selectedOptions).map(o => o.value);
  }

  // =========================================================================
  // Statistics
  // =========================================================================
  function bindStats() {
    $('#btnStatsDesc')?.addEventListener('click', runDescriptiveStats);
    $('#btnStatsNormality')?.addEventListener('click', runNormalityTests);
    $('#btnStatsTest')?.addEventListener('click', runHypothesisTest);
  }

  async function runDescriptiveStats() {
    if (!state.sessionId) return;
    const col = $('#statsColumn')?.value;
    if (!col) return;
    showLoader('Computing…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/stats/descriptive`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ column: col }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      const container = $('#statsDescResult');
      if (container) {
        container.innerHTML = `<div class="stats-grid">${Object.entries(data).map(([k, v]) => `<div class="stat-card"><div class="stat-label">${esc(k)}</div><div class="stat-value">${fmt(v)}</div></div>`).join('')}</div>`;
      }
    } catch (e) { showToast(e.message, 'error'); } finally { hideLoader(); }
  }

  async function runNormalityTests() {
    if (!state.sessionId) return;
    const col = $('#statsNormalityCol')?.value;
    if (!col) return;
    showLoader('Running normality tests…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/stats/normality`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ column: col }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      const container = $('#statsNormalityResult');
      if (container) {
        container.innerHTML = `<div class="stats-tests">${(data.tests || []).map(t => `
          <div class="test-card">
            <div class="test-name">${esc(t.test)}</div>
            ${t.error ? `<div class="test-error">${esc(t.error)}</div>` : `
              <div class="test-stat">Statistic: ${t.statistic}</div>
              <div class="test-p">p-value: ${t.p_value}</div>
              <div class="test-result ${t.is_normal ? 'test-pass' : 'test-fail'}">${t.is_normal ? 'Normal' : 'Not Normal'}</div>
              <div class="test-interpret">${esc(t.interpretation)}</div>
            `}
          </div>
        `).join('')}</div>`;
      }
    } catch (e) { showToast(e.message, 'error'); } finally { hideLoader(); }
  }

  async function runHypothesisTest() {
    if (!state.sessionId) return;
    const testType = $('#statsTestType')?.value;
    const colA = $('#statsColA')?.value;
    const colB = $('#statsColB')?.value;
    if (!colA) return;
    showLoader('Running test…');
    try {
      let endpoint, body;
      if (testType === 'ttest') {
        endpoint = '/stats/ttest';
        body = { column_a: colA, column_b: colB };
      } else if (testType === 'chi-square') {
        endpoint = '/stats/chi-square';
        body = { column_a: colA, column_b: colB };
      } else if (testType === 'correlation') {
        endpoint = '/stats/correlation-test';
        body = { column_a: colA, column_b: colB };
      } else {
        endpoint = '/stats/ttest';
        body = { column_a: colA, column_b: colB };
      }
      const res = await fetch(`${API}/api/session/${state.sessionId}${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      const container = $('#statsTestResult');
      if (container) {
        container.innerHTML = `<div class="test-card"><div class="test-name">${esc(data.test || testType)}</div>
          ${data.error ? `<div class="test-error">${esc(data.error)}</div>` : `
            <div class="test-stat">Statistic: ${data.statistic ?? data.r ?? data.rho ?? 'N/A'}</div>
            <div class="test-p">p-value: ${data.p_value ?? 'N/A'}</div>
            <div class="test-result ${data.significant !== false ? 'test-pass' : 'test-fail'}">${data.significant !== false ? 'Significant' : 'Not Significant'}</div>
            <div class="test-interpret">${esc(data.interpretation || '')}</div>
          `}
        </div>`;
      }
    } catch (e) { showToast(e.message, 'error'); } finally { hideLoader(); }
  }

  // =========================================================================
  // Tools (SQL, Code, Chart Advisor)
  // =========================================================================
  function bindTools() {
    $('#btnGenerateSQL')?.addEventListener('click', generateSQL);
    $('#btnGenerateCode')?.addEventListener('click', generateCode);
    $('#btnChartAdvisor')?.addEventListener('click', getChartRecommendations);
  }

  async function generateSQL() {
    if (!state.sessionId) return;
    const question = $('#sqlQuestion')?.value?.trim();
    const dialect = $('#sqlDialect')?.value || 'MySQL';
    if (!question) return;
    showLoader('Generating SQL…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/sql`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, dialect }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      const container = $('#sqlResult');
      if (container && data.sql) {
        container.innerHTML = `<pre class="tool-code"><code>${esc(data.sql)}</code></pre>
          <div class="tool-explain">${esc(data.explanation || '')}</div>
          <button class="btn btn-sm" onclick="navigator.clipboard.writeText('${esc(data.sql).replace(/'/g, "\\'")}')">Copy SQL</button>`;
      }
    } catch (e) { showToast(e.message, 'error'); } finally { hideLoader(); }
  }

  async function generateCode() {
    if (!state.sessionId) return;
    const question = $('#codeQuestion')?.value?.trim();
    if (!question) return;
    showLoader('Generating code…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/code`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      const container = $('#codeResult');
      if (container && data.code) {
        container.innerHTML = `<pre class="tool-code"><code>${esc(data.code)}</code></pre>
          <div class="tool-explain">${esc(data.explanation || '')}</div>
          <button class="btn btn-sm" onclick="navigator.clipboard.writeText('${esc(data.code).replace(/'/g, "\\'")}')">Copy Code</button>`;
      }
    } catch (e) { showToast(e.message, 'error'); } finally { hideLoader(); }
  }

  async function getChartRecommendations() {
    if (!state.sessionId) return;
    showLoader('Analyzing data…');
    try {
      const res = await fetch(`${API}/api/session/${state.sessionId}/chart-recommendations`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      const container = $('#chartAdvisorResult');
      if (container) {
        container.innerHTML = `<div class="chart-recs">${(data.recommendations || []).slice(0, 8).map(r => `
          <div class="chart-rec-card">
            <div class="chart-rec-type">${iconChart(r.chart_type, '')} ${esc(r.chart_type)}</div>
            <div class="chart-rec-title">${esc(r.title)}</div>
            <div class="chart-rec-reason">${esc(r.reason)}</div>
            <div class="chart-rec-conf">Confidence: ${r.confidence}%</div>
            <button class="btn btn-sm" onclick="document.querySelector('[data-tab=charts]').click(); /* TODO: auto-generate chart */">View</button>
          </div>
        `).join('')}</div>`;
      }
    } catch (e) { showToast(e.message, 'error'); } finally { hideLoader(); }
  }

  // =========================================================================
  // Dashboard Builder
  // =========================================================================
  function bindDashboard() {
    const dashState = {
      dashboards: [],
      currentDashboard: null,
      currentPageIdx: 0,
      selectedWidget: null,
      clipboard: null,
      undoStack: [],
      redoStack: [],
      zoom: 1,
      filters: [],
      isDragging: false,
      dragType: null,
      dragData: null,
    };

    // Toolbar bindings
    $('#dashNew')?.addEventListener('click', () => createNewDashboard());
    $('#dashSave')?.addEventListener('click', () => saveCurrentDashboard());
    $('#dashLoad')?.addEventListener('click', () => showLoadModal());
    $('#dashDuplicate')?.addEventListener('click', () => duplicateCurrentDashboard());
    $('#dashUndo')?.addEventListener('click', () => undoAction());
    $('#dashRedo')?.addEventListener('click', () => redoAction());
    $('#dashAIGenerate')?.addEventListener('click', () => aiGenerateDashboard());
    $('#dashTemplate')?.addEventListener('change', (e) => {
      if (e.target.value) loadTemplate(e.target.value);
      e.target.value = '';
    });
    $('#dashFullscreen')?.addEventListener('click', () => toggleFullscreen());
    $('#dashPresent')?.addEventListener('click', () => togglePresentation());
    $('#dashExport')?.addEventListener('change', (e) => {
      if (e.target.value) exportDashboard(e.target.value);
      e.target.value = '';
    });
    $('#dashAddPage')?.addEventListener('click', () => addPage());
    $('#dashPageSelect')?.addEventListener('change', (e) => switchPage(parseInt(e.target.value)));
    $('#dashAddFilter')?.addEventListener('click', () => showFilterModal());
    $('#dashTitle')?.addEventListener('change', (e) => {
      if (dashState.currentDashboard) {
        pushUndo();
        dashState.currentDashboard.title = e.target.value;
      }
    });

    // Zoom
    $('#dashZoomIn')?.addEventListener('click', () => setZoom(dashState.zoom + 0.1));
    $('#dashZoomOut')?.addEventListener('click', () => setZoom(dashState.zoom - 0.1));
    $('#dashZoomFit')?.addEventListener('click', () => setZoom(1));

    // Widget palette drag
    document.querySelectorAll('.dash-widget-type').forEach(el => {
      el.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('widget-type', el.dataset.type);
        e.dataTransfer.effectAllowed = 'copy';
      });
    });

    // Drop zone
    const dropZone = $('#dashDropZone');
    if (dropZone) {
      dropZone.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
      dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        const type = e.dataTransfer.getData('widget-type');
        if (type) addWidget(type);
      });
    }

    // Context menu
    document.addEventListener('click', () => hideContextMenu());
    $('#dashContextMenu')?.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        handleContextAction(action);
        hideContextMenu();
      });
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      const dashPanel = $('#view-dashboard');
      if (!dashPanel || !dashPanel.classList.contains('active')) return;
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (dashState.selectedWidget) deleteWidget(dashState.selectedWidget);
      }
      if (e.ctrlKey && e.key === 'z') { e.preventDefault(); undoAction(); }
      if (e.ctrlKey && e.key === 'y') { e.preventDefault(); redoAction(); }
      if (e.ctrlKey && e.key === 'c') { e.preventDefault(); copyWidget(); }
      if (e.ctrlKey && e.key === 'v') { e.preventDefault(); pasteWidget(); }
      if (e.key === 'Escape') { deselectWidget(); hideContextMenu(); }
      if (e.key === 'F11') { e.preventDefault(); toggleFullscreen(); }
    });

    // Helper functions
    function pushUndo() {
      if (!dashState.currentDashboard) return;
      dashState.undoStack.push(JSON.stringify(dashState.currentDashboard));
      if (dashState.undoStack.length > 50) dashState.undoStack.shift();
      dashState.redoStack = [];
    }

    function undoAction() {
      if (!dashState.undoStack.length) return;
      dashState.redoStack.push(JSON.stringify(dashState.currentDashboard));
      dashState.currentDashboard = JSON.parse(dashState.undoStack.pop());
      renderDashboard();
    }

    function redoAction() {
      if (!dashState.redoStack.length) return;
      dashState.undoStack.push(JSON.stringify(dashState.currentDashboard));
      dashState.currentDashboard = JSON.parse(dashState.redoStack.pop());
      renderDashboard();
    }

    function setZoom(z) {
      dashState.zoom = Math.max(0.3, Math.min(2, z));
      const canvas = $('#dashCanvas');
      if (canvas) canvas.style.transform = `scale(${dashState.zoom})`;
      $('#dashZoomLevel').textContent = Math.round(dashState.zoom * 100) + '%';
    }

    function createNewDashboard() {
      dashState.currentDashboard = {
        title: 'Untitled Dashboard',
        pages: [{ id: genId(), name: 'Page 1', widgets: [] }],
        filters: [],
        settings: { theme: 'dark', gridColumns: 12, gridRowHeight: 60 },
      };
      dashState.currentPageIdx = 0;
      dashState.undoStack = [];
      dashState.redoStack = [];
      $('#dashTitle').value = dashState.currentDashboard.title;
      renderDashboard();
      showToast('New dashboard created', 'success');
    }

    function genId() { return Math.random().toString(36).substr(2, 8); }

    function getCurrentPage() {
      if (!dashState.currentDashboard) return null;
      return dashState.currentDashboard.pages[dashState.currentPageIdx] || null;
    }

    function addWidget(type) {
      if (!dashState.currentDashboard) createNewDashboard();
      pushUndo();
      const page = getCurrentPage();
      if (!page) return;

      const cols = 12;
      const widgets = page.widgets;
      let maxY = 0;
      widgets.forEach(w => { const bottom = (w.y || 0) + (w.h || 4); if (bottom > maxY) maxY = bottom; });

      const titleMap = {
        bar: 'Bar Chart', stacked_bar: 'Stacked Bar', horizontal_bar: 'Horizontal Bar',
        grouped_bar: 'Grouped Bar', line: 'Line Chart', area: 'Area Chart', spline: 'Spline Chart',
        pie: 'Pie Chart', donut: 'Donut Chart', scatter: 'Scatter Plot', bubble: 'Bubble Chart',
        histogram: 'Histogram', heatmap: 'Heatmap', treemap: 'Treemap', sunburst: 'Sunburst',
        box: 'Box Plot', violin: 'Violin Plot', density: 'Density Plot', radar: 'Radar Chart',
        waterfall: 'Waterfall', funnel: 'Funnel', gauge: 'Gauge', kpi: 'KPI Card',
        data_table: 'Data Table', correlation_heatmap: 'Correlation Heatmap',
        time_series: 'Time Series', forecast: 'Forecast', distribution: 'Distribution', outlier: 'Outlier Chart',
      };

      const widget = {
        id: genId(),
        chart_type: type,
        title: titleMap[type] || type,
        config: {},
        x: 0, y: maxY, w: type === 'kpi' ? 3 : 6, h: type === 'kpi' ? 3 : 5,
      };

      widgets.push(widget);
      renderDashboard();
      showToast(`Added ${titleMap[type] || type}`, 'success');
    }

    function deleteWidget(id) {
      if (!dashState.currentDashboard) return;
      pushUndo();
      const page = getCurrentPage();
      if (!page) return;
      page.widgets = page.widgets.filter(w => w.id !== id);
      dashState.selectedWidget = null;
      renderDashboard();
    }

    function duplicateWidget(id) {
      if (!dashState.currentDashboard) return;
      pushUndo();
      const page = getCurrentPage();
      if (!page) return;
      const orig = page.widgets.find(w => w.id === id);
      if (!orig) return;
      const clone = { ...JSON.parse(JSON.stringify(orig)), id: genId(), x: (orig.x || 0) + 2, y: (orig.y || 0) + 2 };
      page.widgets.push(clone);
      renderDashboard();
    }

    function copyWidget() {
      if (!dashState.selectedWidget || !dashState.currentDashboard) return;
      const page = getCurrentPage();
      if (!page) return;
      const w = page.widgets.find(w => w.id === dashState.selectedWidget);
      if (w) { dashState.clipboard = JSON.parse(JSON.stringify(w)); showToast('Widget copied', 'info'); }
    }

    function pasteWidget() {
      if (!dashState.clipboard || !dashState.currentDashboard) return;
      pushUndo();
      const page = getCurrentPage();
      if (!page) return;
      const clone = { ...JSON.parse(JSON.stringify(dashState.clipboard)), id: genId(), x: (dashState.clipboard.x || 0) + 2, y: (dashState.clipboard.y || 0) + 2 };
      page.widgets.push(clone);
      renderDashboard();
      showToast('Widget pasted', 'success');
    }

    function deselectWidget() {
      dashState.selectedWidget = null;
      document.querySelectorAll('.dash-widget.selected').forEach(el => el.classList.remove('selected'));
    }

    function showContextMenu(e, widgetId) {
      e.preventDefault();
      e.stopPropagation();
      dashState.selectedWidget = widgetId;
      const menu = $('#dashContextMenu');
      if (menu) {
        menu.hidden = false;
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
      }
    }

    function hideContextMenu() {
      const menu = $('#dashContextMenu');
      if (menu) menu.hidden = true;
    }

    function handleContextAction(action) {
      if (!dashState.selectedWidget) return;
      switch (action) {
        case 'configure': showWidgetConfig(dashState.selectedWidget); break;
        case 'duplicate': duplicateWidget(dashState.selectedWidget); break;
        case 'insight': generateWidgetInsight(dashState.selectedWidget); break;
        case 'copy': copyWidget(); break;
        case 'paste': pasteWidget(); break;
        case 'delete': deleteWidget(dashState.selectedWidget); break;
      }
    }

    function showWidgetConfig(widgetId) {
      if (!dashState.currentDashboard) return;
      const page = getCurrentPage();
      if (!page) return;
      const widget = page.widgets.find(w => w.id === widgetId);
      if (!widget) return;

      $('#dashWidgetTitle').value = widget.title || '';
      $('#dashWidgetType').value = widget.chart_type || 'bar';
      $('#dashWidgetAgg').value = widget.config?.agg || 'mean';

      populateConfigSelects();

      if (widget.config?.x) $('#dashWidgetX').value = widget.config.x;
      if (widget.config?.y) $('#dashWidgetY').value = widget.config.y;
      if (widget.config?.color) $('#dashWidgetColor').value = widget.config.color;

      const modal = $('#dashWidgetConfigModal');
      if (modal) modal.hidden = false;

      $('#dashConfigApply').onclick = () => {
        pushUndo();
        widget.title = $('#dashWidgetTitle').value;
        widget.chart_type = $('#dashWidgetType').value;
        widget.config = {
          x: $('#dashWidgetX').value || undefined,
          y: $('#dashWidgetY').value || undefined,
          color: $('#dashWidgetColor').value || undefined,
          agg: $('#dashWidgetAgg').value,
        };
        modal.hidden = true;
        renderDashboard();
      };
    }

    function populateConfigSelects() {
      if (!state.profile) return;
      const cols = state.profile.columns;
      const all = cols.map(c => c.name);
      const numeric = cols.filter(c => c.type === 'numeric').map(c => c.name);
      const categorical = cols.filter(c => c.type === 'categorical').map(c => c.name);

      ['dashWidgetX', 'dashWidgetY'].forEach(id => {
        const sel = $(`#${id}`);
        if (sel) {
          sel.innerHTML = '<option value="">None</option>' + all.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
        }
      });

      const colorSel = $('#dashWidgetColor');
      if (colorSel) {
        colorSel.innerHTML = '<option value="">None</option>' + categorical.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      }

      const filterCol = $('#dashFilterCol');
      if (filterCol) {
        filterCol.innerHTML = all.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      }
    }

    async function generateWidgetInsight(widgetId) {
      if (!state.sessionId || !dashState.currentDashboard) return;
      const page = getCurrentPage();
      if (!page) return;
      const widget = page.widgets.find(w => w.id === widgetId);
      if (!widget) return;
      showLoader('Generating insight...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/chart-insight`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ widget }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        const insight = data.insight;
        showToast(`${insight.summary} — ${insight.findings.length} findings, confidence: ${insight.confidence}%`, 'info');
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    // Page management
    function addPage() {
      if (!dashState.currentDashboard) createNewDashboard();
      pushUndo();
      const idx = dashState.currentDashboard.pages.length + 1;
      dashState.currentDashboard.pages.push({ id: genId(), name: `Page ${idx}`, widgets: [] });
      dashState.currentPageIdx = dashState.currentDashboard.pages.length - 1;
      renderDashboard();
    }

    function switchPage(idx) {
      if (!dashState.currentDashboard) return;
      if (idx >= 0 && idx < dashState.currentDashboard.pages.length) {
        dashState.currentPageIdx = idx;
        renderDashboard();
      }
    }

    // Save/Load
    async function saveCurrentDashboard() {
      if (!state.sessionId || !dashState.currentDashboard) {
        showToast('Create a dashboard first', 'error');
        return;
      }
      dashState.currentDashboard.title = $('#dashTitle')?.value || 'Untitled';
      showLoader('Saving dashboard...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dashboard: dashState.currentDashboard }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        dashState.currentDashboard.id = data.id;
        showToast(`Dashboard saved (v${data.version})`, 'success');
        loadSavedList();
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    async function showLoadModal() {
      if (!state.sessionId) { showToast('Upload a file first', 'error'); return; }
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/list`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        dashState.dashboards = data.dashboards || [];
        const list = $('#dashLoadList');
        if (list) {
          if (!dashState.dashboards.length) {
            list.innerHTML = '<div class="dash-load-empty">No saved dashboards yet.</div>';
          } else {
            list.innerHTML = dashState.dashboards.map(d => `
              <div class="dash-load-item" data-id="${d.id}">
                <div class="dash-load-title">${esc(d.title)}</div>
                <div class="dash-load-meta">${d.pages} pages · v${d.version}</div>
              </div>
            `).join('');
            list.querySelectorAll('.dash-load-item').forEach(item => {
              item.addEventListener('click', () => loadDashboard(item.dataset.id));
            });
          }
        }
        $('#dashLoadModal').hidden = false;
      } catch (e) {
        showToast(e.message, 'error');
      }
    }

    async function loadDashboard(dashId) {
      if (!state.sessionId) return;
      showLoader('Loading dashboard...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/${dashId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        dashState.currentDashboard = data.dashboard;
        dashState.currentPageIdx = 0;
        dashState.undoStack = [];
        dashState.redoStack = [];
        $('#dashTitle').value = dashState.currentDashboard.title || '';
        $('#dashLoadModal').hidden = true;
        renderDashboard();
        showToast('Dashboard loaded', 'success');
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    async function duplicateCurrentDashboard() {
      if (!dashState.currentDashboard?.id) { showToast('Save the dashboard first', 'error'); return; }
      if (!state.sessionId) return;
      showLoader('Duplicating...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/${dashState.currentDashboard.id}/duplicate`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        await loadDashboard(data.id);
        showToast('Dashboard duplicated', 'success');
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    async function loadSavedList() {
      if (!state.sessionId) return;
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/list`);
        const data = await res.json();
        const list = $('#dashSavedList');
        if (!list) return;
        const dashs = data.dashboards || [];
        if (!dashs.length) {
          list.innerHTML = '<p class="dash-empty-text">No saved dashboards</p>';
          return;
        }
        list.innerHTML = dashs.map(d => `
          <div class="dash-saved-item" data-id="${d.id}">
            <span class="dash-saved-title">${esc(d.title)}</span>
            <span class="dash-saved-date">v${d.version}</span>
          </div>
        `).join('');
        list.querySelectorAll('.dash-saved-item').forEach(item => {
          item.addEventListener('click', () => loadDashboard(item.dataset.id));
        });
      } catch (e) { /* ignore */ }
    }

    // AI Generate
    async function aiGenerateDashboard() {
      if (!state.sessionId) { showToast('Upload a file first', 'error'); return; }
      showLoader('AI is generating your dashboard...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/ai-generate`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        dashState.currentDashboard = data.dashboard;
        dashState.currentPageIdx = 0;
        dashState.undoStack = [];
        dashState.redoStack = [];
        $('#dashTitle').value = dashState.currentDashboard.title || 'AI Generated Dashboard';
        renderDashboard();
        showToast('Dashboard generated! Click widgets to configure.', 'success');
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    // Templates
    async function loadTemplate(name) {
      if (!state.sessionId) { showToast('Upload a file first', 'error'); return; }
      showLoader('Loading template...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/template/${name}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        dashState.currentDashboard = data.dashboard;
        dashState.currentPageIdx = 0;
        dashState.undoStack = [];
        dashState.redoStack = [];
        $('#dashTitle').value = dashState.currentDashboard.title || '';
        renderDashboard();
        showToast('Template loaded', 'success');
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    // Fullscreen / Presentation
    function toggleFullscreen() {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    }

    function togglePresentation() {
      document.body.classList.toggle('dash-presenting');
      showToast(document.body.classList.contains('dash-presenting') ? 'Presentation Mode — Press Esc to exit' : 'Exited presentation', 'info');
      const handler = (e) => {
        if (e.key === 'Escape') {
          document.body.classList.remove('dash-presenting');
          document.removeEventListener('keydown', handler);
        }
      };
      document.addEventListener('keydown', handler);
    }

    // Export
    function exportDashboard(format) {
      if (!dashState.currentDashboard) { showToast('No dashboard to export', 'error'); return; }
      if (format === 'json') {
        const blob = new Blob([JSON.stringify(dashState.currentDashboard, null, 2)], { type: 'application/json' });
        downloadBlob(blob, 'dashboard.json');
      } else if (format === 'html') {
        const html = generateExportHTML(dashState.currentDashboard);
        const blob = new Blob([html], { type: 'text/html' });
        downloadBlob(blob, 'dashboard.html');
      } else if (format === 'png' || format === 'pdf') {
        const canvas = $('#dashCanvas');
        if (canvas && typeof html2canvas !== 'undefined') {
          html2canvas(canvas).then(c => {
            c.toBlob(blob => {
              if (blob) downloadBlob(blob, `dashboard.${format}`);
            });
          });
        } else {
          showToast('Export to image requires html2canvas library', 'info');
        }
      } else {
        showToast(`Export as ${format.toUpperCase()} — coming soon`, 'info');
      }
    }

    function downloadBlob(blob, filename) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast(`Exported ${filename}`, 'success');
    }

    function generateExportHTML(dash) {
      let widgetsHTML = '';
      const page = dash.pages?.[0];
      if (page) {
        page.widgets.forEach(w => {
          widgetsHTML += `<div style="position:absolute;left:${(w.x||0)*80}px;top:${(w.y||0)*60}px;width:${(w.w||6)*80}px;height:${(w.h||4)*60}px;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:12px;">
            <h4 style="color:#e6edf3;font-size:13px;margin:0 0 8px;">${esc(w.title)}</h4>
            <div style="color:#8b949e;font-size:12px;">Chart: ${w.chart_type}</div>
          </div>`;
        });
      }
      return `<!DOCTYPE html><html><head><title>${esc(dash.title)}</title><style>body{margin:0;background:#0d1117;font-family:Inter,sans-serif;}</style></head><body><div style="padding:20px;color:#e6edf3;"><h1>${esc(dash.title)}</h1></div><div style="position:relative;height:800px;">${widgetsHTML}</div></body></html>`;
    }

    // Filters
    function showFilterModal() {
      populateConfigSelects();
      $('#dashFilterModal').hidden = false;
      $('#dashFilterApply').onclick = () => {
        const col = $('#dashFilterCol').value;
        const op = $('#dashFilterOp').value;
        const val = $('#dashFilterVal').value;
        if (!col || !val) { showToast('Select column and value', 'error'); return; }
        dashState.filters.push({ column: col, operator: op, value: val });
        $('#dashFilterModal').hidden = true;
        renderFilters();
        applyFilters();
      };
    }

    function renderFilters() {
      const list = $('#dashFilterList');
      if (!list) return;
      if (!dashState.filters.length) {
        list.innerHTML = '<p class="dash-empty-text">No filters active</p>';
        return;
      }
      list.innerHTML = dashState.filters.map((f, i) => `
        <div class="dash-filter-item">
          <span class="dash-filter-info">${esc(f.column)} ${f.operator} ${esc(f.value)}</span>
          <button data-idx="${i}" class="dash-filter-remove">&times;</button>
        </div>
      `).join('');
      list.querySelectorAll('.dash-filter-remove').forEach(btn => {
        btn.addEventListener('click', () => {
          dashState.filters.splice(parseInt(btn.dataset.idx), 1);
          renderFilters();
          applyFilters();
        });
      });
    }

    async function applyFilters() {
      if (!state.sessionId) return;
      if (!dashState.filters.length) {
        renderDashboard();
        return;
      }
      showLoader('Applying filters...');
      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/filter`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filters: dashState.filters }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        showToast(`Filter applied — ${data.row_count.toLocaleString()} rows match`, 'info');
        renderDashboard();
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        hideLoader();
      }
    }

    // Cross-filtering: clicking a chart element filters other charts
    function setupCrossFilter(plotDiv, widgetId) {
      if (!plotDiv) return;
      plotDiv.on('plotly_click', (eventData) => {
        if (!eventData?.points?.length) return;
        const pt = eventData.points[0];
        const filterVal = pt.x || pt.label;
        const filterCol = pt.data?.x?.[0] ? 'x' : null;
        if (filterVal && dashState.currentDashboard) {
          showToast(`Cross-filter: ${filterVal}`, 'info');
        }
      });
    }

    // Drill-down support
    function setupDrillDown(plotDiv, widget) {
      if (!plotDiv) return;
      plotDiv.on('plotly_click', (eventData) => {
        if (!eventData?.points?.length) return;
        const pt = eventData.points[0];
        showToast(`Drill-down: ${pt.x || pt.label || pt.y} — feature coming soon`, 'info');
      });
    }

    // Render dashboard
    function renderDashboard() {
      const page = getCurrentPage();
      const dropZone = $('#dashDropZone');
      if (!dropZone || !page) {
        if (dropZone) dropZone.innerHTML = '<div class="dash-placeholder-text"><p>Create or load a dashboard</p></div>';
        return;
      }

      // Update page selector
      const pageSelect = $('#dashPageSelect');
      if (pageSelect) {
        pageSelect.innerHTML = dashState.currentDashboard.pages.map((p, i) =>
          `<option value="${i}" ${i === dashState.currentPageIdx ? 'selected' : ''}>${esc(p.name)}</option>`
        ).join('');
      }

      if (!page.widgets.length) {
        dropZone.innerHTML = '<div class="dash-placeholder-text"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".3"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg><p>Drag widgets here or click AI Generate</p></div>';
        return;
      }

      let html = '';
      const gridUnit = 80;
      const rowH = 60;

      page.widgets.forEach(widget => {
        const x = (widget.x || 0) * gridUnit;
        const y = (widget.y || 0) * rowH;
        const w = (widget.w || 6) * gridUnit;
        const h = (widget.h || 4) * rowH;

        html += `
          <div class="dash-widget ${dashState.selectedWidget === widget.id ? 'selected' : ''}"
               data-id="${widget.id}"
               style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;">
            <div class="dash-widget-header" data-drag-id="${widget.id}">
              <span class="dash-widget-title">${esc(widget.title)}</span>
              <div class="dash-widget-actions">
                <button data-cfg="${widget.id}" title="Configure">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
                </button>
                <button data-del="${widget.id}" title="Delete">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
            <div class="dash-widget-body" id="widget-body-${widget.id}">
              <div class="chart-placeholder"><div class="loader-spinner"></div></div>
            </div>
            <div class="dash-resize-handle" data-resize="${widget.id}"></div>
          </div>`;
      });

      dropZone.innerHTML = html;

      // Bind events
      page.widgets.forEach(widget => {
        const bodyEl = $(`#widget-body-${widget.id}`);
        const widgetEl = bodyEl?.closest('.dash-widget');
        if (!bodyEl || !widgetEl) return;

        // Click to select
        widgetEl.addEventListener('click', (e) => {
          if (e.target.closest('.dash-widget-actions')) return;
          deselectWidget();
          dashState.selectedWidget = widget.id;
          widgetEl.classList.add('selected');
        });

        // Context menu
        widgetEl.addEventListener('contextmenu', (e) => showContextMenu(e, widget.id));

        // Drag
        const header = widgetEl.querySelector('.dash-widget-header');
        if (header) {
          let startX, startY, origX, origY;
          header.addEventListener('mousedown', (e) => {
            if (e.target.closest('.dash-widget-actions')) return;
            startX = e.clientX; startY = e.clientY;
            origX = widget.x || 0; origY = widget.y || 0;
            const onMove = (ev) => {
              const dx = Math.round((ev.clientX - startX) / gridUnit);
              const dy = Math.round((ev.clientY - startY) / rowH);
              widget.x = Math.max(0, origX + dx);
              widget.y = Math.max(0, origY + dy);
              widgetEl.style.left = widget.x * gridUnit + 'px';
              widgetEl.style.top = widget.y * rowH + 'px';
            };
            const onUp = () => {
              document.removeEventListener('mousemove', onMove);
              document.removeEventListener('mouseup', onUp);
              pushUndo();
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
          });
        }

        // Resize
        const resizeHandle = widgetEl.querySelector('.dash-resize-handle');
        if (resizeHandle) {
          resizeHandle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            const startX = e.clientX, startY = e.clientY;
            const origW = widget.w || 6, origH = widget.h || 4;
            const onMove = (ev) => {
              widget.w = Math.max(2, origW + Math.round((ev.clientX - startX) / gridUnit));
              widget.h = Math.max(2, origH + Math.round((ev.clientY - startY) / rowH));
              widgetEl.style.width = widget.w * gridUnit + 'px';
              widgetEl.style.height = widget.h * rowH + 'px';
            };
            const onUp = () => {
              document.removeEventListener('mousemove', onMove);
              document.removeEventListener('mouseup', onUp);
              pushUndo();
              renderDashboard();
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
          });
        }

        // Widget config buttons
        widgetEl.querySelector('[data-cfg]')?.addEventListener('click', (e) => {
          e.stopPropagation();
          showWidgetConfig(widget.id);
        });
        widgetEl.querySelector('[data-del]')?.addEventListener('click', (e) => {
          e.stopPropagation();
          deleteWidget(widget.id);
        });

        // Render chart
        renderWidgetChart(widget, bodyEl);
      });
    }

    async function renderWidgetChart(widget, bodyEl) {
      if (!state.sessionId || !bodyEl) return;

      // KPI special rendering
      if (widget.chart_type === 'kpi') {
        try {
          const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/chart`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ widget }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail);

          let kpiValue = '—';
          if (data.spec?.layout?.annotations?.[0]?.text) {
            kpiValue = data.spec.layout.annotations[0].text;
          }
          const col = widget.config?.x;
          const trend = col && state.profile ? getTrend(col) : null;

          bodyEl.innerHTML = `
            <div class="dash-kpi-widget">
              <div class="dash-kpi-label">${esc(widget.title)}</div>
              <div class="dash-kpi-value">${esc(kpiValue)}</div>
              ${trend ? `<div class="dash-kpi-trend ${trend.dir}">${trend.icon} ${trend.text}</div>` : ''}
            </div>`;
        } catch (e) {
          bodyEl.innerHTML = `<div class="dash-kpi-widget"><div class="dash-kpi-label">${esc(widget.title)}</div><div class="dash-kpi-value">—</div></div>`;
        }
        return;
      }

      // Data table special rendering
      if (widget.chart_type === 'data_table') {
        try {
          const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/chart`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ widget }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail);
          if (data.spec?.data?.[0]) {
            const trace = data.spec.data[0];
            const headers = trace.header?.values || [];
            const cells = trace.cells?.values || [];
            let tableHTML = '<table><thead><tr>' + headers.map(h => `<th>${esc(h)}</th>`).join('') + '</tr></thead><tbody>';
            const numRows = cells[0]?.length || 0;
            for (let i = 0; i < numRows; i++) {
              tableHTML += '<tr>' + cells.map(col => `<td>${esc(String(col[i] ?? ''))}</td>`).join('') + '</tr>';
            }
            tableHTML += '</tbody></table>';
            bodyEl.innerHTML = `<div class="dash-table-widget">${tableHTML}</div>`;
          }
        } catch (e) {
          bodyEl.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
        }
        return;
      }

      // Regular Plotly charts
      const chartDivId = `chart-${widget.id}`;
      bodyEl.innerHTML = `<div id="${chartDivId}" style="width:100%;height:100%;"></div>`;

      try {
        const res = await fetch(`${API}/api/session/${state.sessionId}/dashboard/chart`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ widget }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        const plotDiv = document.getElementById(chartDivId);
        if (plotDiv) {
          Plotly.newPlot(chartDivId, data.spec.data, data.spec.layout, {
            responsive: true,
            displayModeBar: false,
            staticPlot: false,
          });
          setupCrossFilter(plotDiv, widget.id);
          setupDrillDown(plotDiv, widget);
        }
      } catch (e) {
        bodyEl.innerHTML = `<div class="chart-placeholder"><p style="color:var(--red)">${esc(e.message)}</p></div>`;
      }
    }

    function getTrend(col) {
      if (!state.profile) return null;
      const colInfo = state.profile.columns.find(c => c.name === col);
      if (!colInfo || colInfo.type !== 'numeric') return null;
      const mean = colInfo.mean || 0;
      const median = colInfo.median || 0;
      if (mean > median * 1.1) return { dir: 'up', icon: '↑', text: 'Skewed high' };
      if (mean < median * 0.9) return { dir: 'down', icon: '↓', text: 'Skewed low' };
      return { dir: 'flat', icon: '→', text: 'Balanced' };
    }

    // Modal close buttons
    document.querySelectorAll('.dash-modal-close, [data-close]').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.close;
        if (target) $(`#${target}`).hidden = true;
        else btn.closest('.dash-modal').hidden = true;
      });
    });

    // Init saved list when dashboard tab is activated
    return {
      loadSavedList,
      createNewDashboard,
      renderDashboard,
    };
  }
  function showLoader(msg) { loaderText.textContent = msg; loader.hidden = false; }
  function hideLoader() { loader.hidden = true; }

  let toastTimer;
  function showToast(msg, type) {
    toast.textContent = msg;
    toast.className = 'toast ' + (type || 'info');
    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add('show'));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => { toast.hidden = true; }, 400);
    }, 3500);
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  }

  function fmt(v) {
    if (v == null) return '—';
    if (typeof v === 'number') {
      if (Math.abs(v) >= 1e6) return v.toExponential(2);
      return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 3 });
    }
    return esc(String(v));
  }

  function p_n(n) { return Number(n).toLocaleString(); }

  function iconChart(type, cls) {
    const paths = {
      bar: '<rect x="3" y="10" width="4" height="11" rx="1"/><rect x="10" y="4" width="4" height="17" rx="1"/><rect x="17" y="14" width="4" height="7" rx="1"/>',
      barv: '<rect x="3" y="14" width="4" height="7" rx="1"/><rect x="10" y="8" width="4" height="13" rx="1"/><rect x="17" y="11" width="4" height="10" rx="1"/>',
      scatter: '<circle cx="5" cy="18" r="2"/><circle cx="10" cy="10" r="2"/><circle cx="15" cy="14" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="8" cy="15" r="2"/>',
      line: '<polyline points="3 17 8 11 13 14 21 5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="3" cy="17" r="1.5"/><circle cx="8" cy="11" r="1.5"/><circle cx="13" cy="14" r="1.5"/><circle cx="21" cy="5" r="1.5"/>',
      box: '<rect x="4" y="8" width="6" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="2"/><line x1="7" y1="4" x2="7" y2="8" stroke="currentColor" stroke-width="2"/><line x1="7" y1="17" x2="7" y2="20" stroke="currentColor" stroke-width="2"/><rect x="14" y="11" width="6" height="7" rx="1" fill="none" stroke="currentColor" stroke-width="2"/><line x1="17" y1="7" x2="17" y2="11" stroke="currentColor" stroke-width="2"/><line x1="17" y1="18" x2="17" y2="20" stroke="currentColor" stroke-width="2"/>',
      pie: '<path d="M12 2a10 10 0 1010 10h-10z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2v10h10A10 10 0 0012 2z" fill="currentColor" opacity=".3"/>',
    };
    return `<div class="sug-icon ${cls}"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">${paths[type] || paths.bar}</svg></div>`;
  }

  // ---------- Go ----------
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
