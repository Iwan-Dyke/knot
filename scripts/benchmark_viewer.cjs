/* Benchmark an exported PyVis page without changing the production viewer.
 * Requires Playwright and its Chromium browser in a separate test environment.
 * NODE_PATH=/tmp/knot-viewer-benchmark-run/node_modules \
 * PLAYWRIGHT_BROWSERS_PATH=/tmp/knot-viewer-benchmark-run/browsers \
 * node scripts/benchmark_viewer.cjs input.html [output-directory] [repeats=3]
 * Set LD_LIBRARY_PATH too if browser system libraries are unpacked separately.
 * KNOT_BENCH_VARIANTS=current,static_frozen_solid_themes selects a subset.
 * KNOT_BENCH_CANDIDATE=/path/to/new.html adds a candidate export for paired runs.
 * Initial layout includes document loading; FPS measures scripted pan/zoom.
 * Idle CPU covers two seconds immediately after the loading overlay closes.
 * Redraw timings use shared node coordinates and stop physics in every variant.
 * Headless software-rendering FPS is not a prediction of desktop-browser FPS.
 * Output defaults to a new private temporary directory, printed before measurement.
 * Output pages contain the same private evidence as the input. Keep them local.
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { pathToFileURL } = require('node:url');

let variants = {
  current: {},
  static_curves: { staticCurves: true },
  no_shadows: { noShadows: true },
  frozen: { freeze: true },
  combined: { staticCurves: true, noShadows: true, freeze: true },
  combined_no_edge_labels: {
    staticCurves: true, noShadows: true, freeze: true, noEdgeLabels: true,
  },
  combined_theme_links_on_demand: {
    // Isolate their drawing cost; an on-demand reveal interface is not implemented.
    staticCurves: true, noShadows: true, freeze: true, hideThemeLinks: true,
  },
  static_frozen_solid_themes: {
    staticCurves: true, freeze: true, themeDashes: false,
  },
  static_frozen_long_theme_dashes: {
    staticCurves: true, freeze: true, themeDashes: [8, 16],
  },
};
if (process.env.KNOT_BENCH_CANDIDATE) variants.candidate = {};
// An optional subset lets a follow-up experiment retain a measured control.
if (process.env.KNOT_BENCH_VARIANTS) {
  variants = Object.fromEntries(process.env.KNOT_BENCH_VARIANTS.split(',').map(name => {
    if (!Object.hasOwn(variants, name)) throw Error('Unknown variant: '+name);
    return [name, variants[name]];
  }));
}

function instrument(html, config) {
  const needle = 'network = new vis.Network(container, data, options);';
  if (html.split(needle).length !== 2) throw Error('Unexpected PyVis template');
  return html.replace(needle, `
    const variant = ${JSON.stringify(config)};
    if (variant.staticCurves) options.edges.smooth = {enabled:true, type:'continuous'};
    if (variant.noShadows) nodes.update(nodes.getIds().map(id => ({id, shadow:false})));
    if (variant.noEdgeLabels) edges.update(edges.getIds().map(id => ({id, label:''})));
    if (variant.hideThemeLinks) edges.update(edges.get().filter(e=>e.organisation)
      .map(e => ({id:e.id, hidden:true})));
    if ('themeDashes' in variant) edges.update(edges.get().filter(e=>e.organisation)
      .map(e => ({id:e.id, dashes:variant.themeDashes})));
    allNodes = nodes.get({returnType:'Object'});
    allEdges = edges.get({returnType:'Object'});
    window.bench = {draws:0, initialLayoutMs:null, constructorMs:null};
    const start = performance.now();
    network = new vis.Network(container, data, options);
    bench.constructorMs = performance.now() - start;
    network.on('afterDrawing', () => bench.draws++);
    const ready = () => {
      if (bench.initialLayoutMs !== null) return;
      bench.initialLayoutMs = performance.now();
      if (variant.freeze) network.setOptions({physics:{enabled:false}});
    };
    network.once('stabilizationIterationsDone', ready);
    network.once('stabilized', ready);
  `);
}

function summarise(runs) {
  const median = values => {
    values.sort((a,b)=>a-b);
    const middle = Math.floor(values.length/2);
    return values.length%2 ? values[middle] : (values[middle-1]+values[middle])/2;
  };
  return Object.keys(variants).map(variant => {
    const matching = runs.filter(run=>run.variant===variant);
    return {
      variant, runs:matching.length,
      layout_ms:Math.round(median(matching.map(r=>r.initial.initial_layout_ms))),
      pan_zoom_fps:Number(median(matching.map(r=>r.interaction.frames_per_second)).toFixed(1)),
      idle_main_thread_percent:Number(median(matching.map(r=>
        100*r.idle.main_thread_ms/r.idle.measurement_interval_ms)).toFixed(1)),
      filter_handler_ms:matching[0].controls ? Number(median(matching.flatMap(r=>
        r.controls.filter.map(s=>s.handler_ms))).toFixed(1)) : null,
      filter_paint_ms:matching[0].controls ? Number(median(matching.flatMap(r=>
        r.controls.filter.map(s=>s.paint_ms))).toFixed(1)) : null,
      search_handler_ms:matching[0].controls ? Number(median(matching.flatMap(r=>
        r.controls.search.map(s=>s.handler_ms))).toFixed(1)) : null,
      live_fps:matching[0].live ? Number(median(matching.map(r=>r.live.fps)).toFixed(1)) : null,
    };
  });
}

async function metrics(cdp) {
  const { metrics } = await cdp.send('Performance.getMetrics');
  return Object.fromEntries(metrics.map(({ name, value }) => [name, value]));
}

async function measure(browser, file, referencePositions, screenshot) {
  const context = await browser.newContext({ viewport: {width:1440, height:1000}, deviceScaleFactor:1 });
  const blocked = [], errors = [];
  await context.route(/https?:\/\//, route => {
    blocked.push(route.request().url());
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const cdp = await context.newCDPSession(page);
  await cdp.send('Performance.enable');
  try {
    await page.goto(pathToFileURL(file).href, {waitUntil:'load', timeout:60000});
    await page.waitForFunction(() => window.bench?.initialLayoutMs !== null &&
      window.bench?.initialLayoutMs !== undefined, null, {timeout:60000});
    await page.waitForFunction(() => !document.getElementById('loadingBar') ||
      getComputedStyle(document.getElementById('loadingBar')).display === 'none',
      null, {timeout:60000});
    const initial = await page.evaluate(() => ({
      initial_layout_ms:bench.initialLayoutMs,
      constructor_ms:bench.constructorMs,
      nodes:nodes.length, edges:edges.length,
      theme_edges:edges.get().filter(e => e.organisation).length,
      visible_edges:edges.get().filter(e => !e.hidden).length,
      internal_support_nodes:Object.keys(network.body.nodes).length - nodes.length,
      physics_support_nodes:(network.physics.physicsBody.physicsNodeIndices || [])
        .filter(id=>!nodes.get(id)).length,
    }));
    const before = await metrics(cdp);
    const start = await page.evaluate(() => ({time:performance.now(), draws:bench.draws}));
    await page.waitForTimeout(2000);
    const stop = await page.evaluate(() => ({time:performance.now(), draws:bench.draws}));
    const after = await metrics(cdp);
    const idle = {
      elapsed_ms:stop.time-start.time,
      measurement_interval_ms:(after.Timestamp-before.Timestamp)*1000,
      main_thread_ms:(after.TaskDuration-before.TaskDuration)*1000,
      draws:stop.draws-start.draws,
    };
    const positions = referencePositions || await page.evaluate(() => network.getPositions());
    const interaction = await page.evaluate(async () => {
      const intervals = [];
      const centre = network.getViewPosition(), scale = network.getScale();
      const start = performance.now();
      let previous = start;
      await new Promise(resolve => {
        function frame(now) {
          intervals.push(now-previous); previous=now;
          const phase = (now-start)/3000*Math.PI*2;
          network.moveTo({position:{x:centre.x+Math.sin(phase)*180,
            y:centre.y+Math.cos(phase)*100}, scale:scale*(1.1+0.1*Math.sin(phase)),
            animation:false});
          if (now-start < 3000) requestAnimationFrame(frame); else resolve();
        }
        requestAnimationFrame(frame);
      });
      intervals.sort((a,b)=>a-b);
      return {
        frames:intervals.length, elapsed_ms:previous-start,
        frames_per_second:intervals.length*1000/(previous-start),
        p95_frame_ms:intervals[Math.floor(intervals.length*0.95)],
      };
    });
    // Fix identical geometry and stop physics to isolate canvas rendering cost.
    await page.evaluate(positions => {
      network.setOptions({physics:{enabled:false}});
      nodes.update(Object.entries(positions).map(([id,p]) => ({id,...p})));
      network.fit({animation:false});
    }, positions);
    const redraw = await page.evaluate(() => {
      const times = [];
      for (let i=0; i<25; i++) {
        const start=performance.now(); network.redraw();
        if (i>=5) times.push(performance.now()-start);
      }
      times.sort((a,b)=>a-b);
      return {median_ms:times[Math.floor(times.length/2)], p95_ms:times[Math.floor(times.length*0.95)]};
    });
    const controls = await page.evaluate(async () => {
      if (!window.knotViewer) return null;
      const frame = () => new Promise(resolve=>requestAnimationFrame(resolve));
      const samples = {filter:[], search:[]};
      for (let i=0; i<8; i++) {
        await frame();
        const start=performance.now(); document.querySelector('#theme-filters input').click();
        const handler_ms=performance.now()-start;
        await frame(); await frame();
        samples.filter.push({handler_ms, paint_ms:performance.now()-start});
      }
      for (let i=0; i<8; i++) {
        await frame(); const start=performance.now();
        const input=document.getElementById('entity-search');
        input.value=i%2 ? '' : 'a'; input.dispatchEvent(new Event('input',{bubbles:true}));
        const handler_ms=performance.now()-start;
        await frame(); await frame();
        samples.search.push({handler_ms, paint_ms:performance.now()-start});
      }
      return samples;
    });
    const live = await page.evaluate(async () => {
      const toggle=document.getElementById('animate-layout');
      if (!toggle) return null;
      toggle.click(); let frames=0;
      const start=performance.now();
      await new Promise(resolve=>{
        function frame(now) {
          frames++;
          if (now-start<2000) requestAnimationFrame(frame); else resolve();
        }
        requestAnimationFrame(frame);
      });
      const elapsed=performance.now()-start;
      document.getElementById('pause-layout').click();
      return {frames, elapsed_ms:elapsed, fps:frames*1000/elapsed};
    });
    // Restore identical geometry after the live-layout measurement for screenshots.
    await page.evaluate(positions => {
      nodes.update(Object.entries(positions).map(([id,p])=>({id,...p})));
      network.fit({animation:false});
    }, positions);
    // Check that the rendering experiment has not removed claims or evidence.
    const functional = await page.evaluate(() => {
      const claim = edges.get().find(e => !e.organisation);
      const originalPosition = network.getPosition(claim.from);
      if (window.knotViewer) knotViewer.inspectNode(claim.from);
      else selectNode([claim.from]);
      const selected = network.getSelectedNodes().includes(claim.from);
      if (window.knotViewer) network.unselectAll();
      else neighbourhoodHighlight({nodes:[]});
      network.moveNode(claim.from, originalPosition.x+20, originalPosition.y+20);
      const movable = Math.abs(network.getPosition(claim.from).x-originalPosition.x-20)<0.01;
      network.moveNode(claim.from, originalPosition.x, originalPosition.y);
      return {selection:selected, node_movement:movable,
        all_claims_have_evidence:edges.get().filter(e=>!e.organisation)
          .every(e=>e.title.includes('<b>quote:</b>') && e.title.includes('<b>status:</b>'))};
    });
    if (screenshot) await page.screenshot({path:screenshot, fullPage:true});
    return {initial,idle,interaction,redraw,controls,live,functional,blocked_requests:blocked,errors,positions};
  } finally {
    await context.close();
  }
}

async function prepareBenchmark(args) {
  if (!args[0] || args.length > 3) {
    throw Error('Usage: node scripts/benchmark_viewer.cjs input.html [output-directory] [repeats=3]');
  }
  const input = path.resolve(args[0]);
  const repeats = Number(args[2] ?? 3);
  if (!Number.isInteger(repeats) || repeats < 1) throw Error('Repeats must be a positive integer');
  const html = await fs.readFile(input, 'utf8');
  const output = args[1] ? path.resolve(args[1])
    : await fs.mkdtemp(path.join(os.tmpdir(), 'knot-viewer-benchmark-'));
  if (args[1]) await fs.mkdir(output, {recursive:true, mode:0o700});
  return {input, output, repeats, html};
}

async function main() {
  const {output, repeats, html} = await prepareBenchmark(process.argv.slice(2));
  console.log('Benchmark artifacts: ' + output);
  const { chromium } = require('playwright');
  const candidate = process.env.KNOT_BENCH_CANDIDATE
    ? await fs.readFile(path.resolve(process.env.KNOT_BENCH_CANDIDATE),'utf8') : null;
  for (const [name, config] of Object.entries(variants)) {
    await fs.writeFile(path.join(output, name+'.html'), instrument(name==='candidate' ? candidate : html, config));
  }
  const browser = await chromium.launch({headless:true});
  const browserSession = await browser.newBrowserCDPSession();
  const system = await browserSession.send('SystemInfo.getInfo');
  const result = {
    measured_at:new Date().toISOString(), input_sha256:createHash('sha256').update(html).digest('hex'),
    candidate_sha256:candidate ? createHash('sha256').update(candidate).digest('hex') : null,
    environment:{browser:browser.version(), platform:os.platform(), release:os.release(),
      cpu:os.cpus()[0].model, cpus:os.cpus().length, viewport:'1440x1000', headless:true},
    graphics:{devices:system.gpu.devices, features:system.gpu.featureStatus},
    variants, runs:[],
  };
  const names = Object.keys(variants);
  let referencePositions;
  try {
    for (let repeat=0; repeat<repeats; repeat++) {
      // Rotate the order to avoid always measuring one variant on a cold browser.
      const order = names.slice(repeat % names.length).concat(names.slice(0, repeat % names.length));
      for (const name of order) {
        const data = await measure(browser, path.join(output,name+'.html'), referencePositions,
          repeat===0 ? path.join(output,name+'.png') : null);
        referencePositions ||= data.positions;
        delete data.positions;
        result.runs.push({variant:name, repeat,...data});
        await fs.writeFile(path.join(output,'results.json'),JSON.stringify(result,null,2)+'\n');
        console.log(JSON.stringify({variant:name,repeat,layout_ms:Math.round(data.initial.initial_layout_ms),
          idle_cpu_ms:Math.round(data.idle.main_thread_ms),fps:Math.round(data.interaction.frames_per_second),
          redraw_ms:Math.round(data.redraw.median_ms),functional:data.functional,errors:data.errors}));
      }
    }
  } finally {
    await browser.close();
  }
  result.summary = summarise(result.runs);
  await fs.writeFile(path.join(output,'results.json'),JSON.stringify(result,null,2)+'\n');
  console.table(result.summary);
  if (result.runs.some(r=>r.errors.length || r.blocked_requests.length ||
      Object.values(r.functional).some(value=>!value))) {
    throw Error('Functional checks failed; inspect results.json');
  }
}

module.exports = {prepareBenchmark};
if (require.main === module) {
  main().catch(error => {console.error(error);process.exitCode=1;});
}
