// Grafana's plugin loader provides React and the SDK as AMD modules.
define(['react', '@grafana/data', '@grafana/runtime'], function (React, sdk, runtime) {
  'use strict';
  const h = React.createElement;
  const colors = ['#246b4b', '#8a6300', '#a82d35'];
  const states = ['Healthy', 'Attention', 'Critical'];
  const ruleEndpoint = '/api/prometheus/grafana/api/v1/rules';

  function result(check, level, status, url, observed) {
    return { name: check.name, level, status, url, observed };
  }

  function assess(check, rules, samples, now, range) {
    const fallback = result(check, 1, 'No current evidence');
    if (check.gap) return result(check, 1, 'No functional probe configured');
    if (check.rule) {
      const rule = rules.get(check.rule);
      if (!rule) return fallback;
      const { annotations = {}, totals = {} } = rule;
      const uid = annotations.__dashboardUid__;
      const panel = annotations.__panelId__;
      const url = uid ? '/d/' + encodeURIComponent(uid) + '/_?' + range +
        (panel ? '&viewPanel=' + encodeURIComponent(panel) : '') :
        check.rule === 'autobrr_irc_channel_unmonitored' ? '/d/autobrr-metrics/_?' + range :
        check.rule === 'sunday_edge_dfs_autoscaler_stale' ? '/d/sunday-edge-dfs-compute/_?' + range :
        '/alerting/grafana/' + encodeURIComponent(check.rule) + '/view';
      const observed = Date.parse(rule.lastEvaluation);
      const row = (level, status) => result(check, level, status, url, observed);
      if (rule.isPaused) return row(1, 'Evaluation paused');
      if (!Number.isFinite(observed) || now - observed > Math.max(120, rule.interval * 3) * 1000) return row(1, 'Evaluation stale');
      if (totals.alerting || totals.firing || rule.state === 'firing') {
        if (rule.health !== 'ok' || /telemetry (missing|unavailable)|metrics missing|expected host telemetry missing/i.test(check.name)) return row(1, 'Telemetry unavailable');
        const firing = (rule.alerts || []).filter(a => /alerting|firing/i.test(a.state));
        const details = firing.slice(0, 3).map(a => [a.labels?.name || a.labels?.instance, a.value].filter(Boolean).join(' ')).filter(Boolean);
        return row(rule.labels?.severity === 'critical' ? 2 : 1, ['Firing', ...details].join(' · '));
      }
      if (rule.health !== 'ok' || totals.error || totals.nodata || totals.no_data) return row(1, 'Evaluation ' + rule.health);
      if (rule.state === 'pending' || totals.pending || totals.recovering) return row(1, 'Pending or recovering');
      return rule.state === 'inactive' && totals.normal ? row(0, 'Normal') : row(1, 'Unconfirmed');
    }
    const key = check.monitor ? 'kuma-' + check.monitor : check.container ? 'container-' + check.container :
      check.job ? 'job-' + check.job : check.signal;
    const sample = samples.get(key);
    const url = check.monitor ? 'https://uptime.benlawson.dev/dashboard/' + check.monitor :
      check.container ? '/d/fdw07wwnc7y0wa/_?' + range :
      check.signal === 'mount' ? '/d/qnap-nas/_?' + range : '/connections/datasources/edit/adw07verg2qrkd';
    const row = (level, status) => result(check, level, status, url, sample?.time);
    if (!sample || now - sample.time > 150000 || !Number.isFinite(sample.value)) return row(1, 'Sample missing or stale');
    if (check.container) return now - sample.value * 1000 < 120000 ? row(0, 'Container observed') : row(1, 'Container observation stale');
    if (check.monitor) {
      if (sample.value === 1) return row(0, 'Up');
      if (sample.value === 0) return row(check.secondary ? 1 : 2, 'Down');
      return row(1, sample.value === 3 ? 'Maintenance' : 'Pending or unknown');
    }
    return sample.value === 1 ? row(0, check.job ? 'Scraping' : 'Mounted') :
      row(check.job ? 1 : 2, check.job ? 'Scrape failed' : 'Mount unavailable');
  }

  function HealthPanel({ options, data, timeRange, width, height }) {
    const [rules, setRules] = React.useState(new Map());
    const selection = () => new URLSearchParams(location.search).get('var-healthArea');
    const [selected, select] = React.useState(selection);
    React.useEffect(() => {
      const sync = () => select(selection());
      window.addEventListener('popstate', sync);
      return () => window.removeEventListener('popstate', sync);
    }, []);
    React.useEffect(() => {
      let active = true;
      let timer;
      async function refresh() {
        try {
          const response = await runtime.getBackendSrv().get(ruleEndpoint);
          const current = new Map();
          for (const group of response.data.groups) {
            for (const rule of group.rules) current.set(rule.uid, { ...rule, group: group.name, interval: group.interval });
          }
          if (active) setRules(current);
        } catch {
          if (active) setRules(new Map());
        } finally {
          if (active) timer = setTimeout(refresh, 30000);
        }
      }
      refresh();
      return () => { active = false; clearTimeout(timer); };
    }, []);
    function navigate(name) {
      const params = new URLSearchParams(location.search);
      if (name) params.set('var-healthArea', name);
      else params.delete('var-healthArea');
      runtime.locationService.push(location.pathname + '?' + params);
      select(name);
    }
    const range = new URLSearchParams({ from: timeRange.from.valueOf(), to: timeRange.to.valueOf() }).toString();
    const samples = new Map();
    for (const frame of data.series) {
      const field = frame.fields.find(f => f.type === 'number');
      const time = frame.fields.find(f => f.type === 'time');
      if (!field || !time || !field.values.length) continue;
      const i = field.values.length - 1;
      const name = sdk.getFieldDisplayName(field, frame, data.series);
      samples.set(name, { time: Number(time.values[i]), value: field.values[i] });
    }
    const now = Date.now();
    const areas = options.areas.map(area => {
      const indicators = [...area.checks];
      for (const group of area.ruleGroups) {
        const matching = Array.from(rules.values()).filter(rule => rule.group === group.name);
        for (const rule of matching) indicators.push({ name:rule.name, rule:rule.uid });
        for (const uid of group.expected) {
          if (!rules.has(uid)) indicators.push({ name:uid.replaceAll('_',' '), rule:uid });
        }
      }
      const checks = indicators.map(check => assess(check, rules, samples, now, range)).sort((a,b) => b.level - a.level);
      let level = Math.max(...checks.map(c => c.level));
      if (area.name === 'Network & DNS' && [246,247].every(id => {
        const probe = samples.get('kuma-' + id);
        return probe?.value === 0 && now - probe.time < 150000;
      })) level = 2;
      return { ...area, checks, level };
    });
    const area = areas.find(a => a.name === selected);
    const columns = Math.max(1, Math.min(5, Math.floor((width - 30) / 140)));
    const tileWidth = Math.min(155, (width - 30) / (columns + 0.5));
    const section = (title, items) => {
      const rows = [];
      for (let i = 0; i < items.length; i += columns) rows.push(items.slice(i, i + columns));
      return h('section', { key: title, style:{ marginBottom:24 } },
      h('h3', null, title), rows.map((row, index) => h('div', { key:index, style: {
        display:'flex', gap:3, marginTop:index ? -24 : 0, marginLeft:index % 2 ? tileWidth/2 : 0
      } }, row.map(a => h('button', {
          key:a.name, type:'button', onClick:() => navigate(a.name),
          'aria-label':a.name + ', ' + states[a.level], title:a.name + ' · ' + states[a.level],
          style:{ clipPath:'polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%)',
            width:tileWidth, height:118, background:colors[a.level],
            color:'white', border:0, padding:'0 10px', fontSize:15, fontWeight:600, lineHeight:1.2, cursor:'pointer' }
        }, a.name)))));
    };
    return h('div', { style:{ overflow:'auto',height,padding:12 } }, area ?
      h(React.Fragment,null,h('button',{type:'button',onClick:() => navigate(null)},'← All areas'),
        h('h2',{style:{marginTop:15}},area.name),
        area.dependencies.length > 0 && h('p',null,'Related health · ',area.dependencies.map((name,i) =>
          h(React.Fragment,{key:name},i > 0 ? ' · ' : '',h('a',{href:'?'+range+'&var-healthArea='+encodeURIComponent(name),
            onClick:e=>{ if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); navigate(name); } }},name)))),
        h('table',{style:{width:'100%',textAlign:'left'}},
          h('thead',null,h('tr',null,['Indicator','Status','Last observed'].map(t=>h('th',{key:t},t)))),
          h('tbody',null,area.checks.map(c=>h('tr',{key:c.name},
            h('td',{style:{padding:'8px 4px'}},c.url ? h('a',{href:c.url,style:{textDecoration:'underline'}},c.name) : c.name),
            h('td',null,h('span',{style:{color:'white',background:colors[c.level],padding:'2px 6px'}},c.status)),
            h('td',null,c.observed ? new Date(c.observed).toLocaleTimeString() : '—')))))) :
      h(React.Fragment,null,section('Services',areas.slice(0,8)),section('Infrastructure',areas.slice(8)),
        h('small',null,'Green · healthy     Yellow · degraded or unverified     Red · critical')));
  }
  return { plugin: new sdk.PanelPlugin(HealthPanel) };
});
