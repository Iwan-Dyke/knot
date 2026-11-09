/* Optional browser checks, using the existing external Playwright environment.
 * NODE_PATH=... PLAYWRIGHT_BROWSERS_PATH=... node scripts/test_viewer_browser.cjs
 * An optional argument exercises a real exported snapshot too.
 * HTTP requests are blocked; screenshots and the synthetic HTML stay in /tmp.
 */
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'knot-viewer-check-'));
  const file = path.join(output, 'synthetic.html');
  execFileSync(path.join(root, '.venv/bin/python'), [path.join(root, 'tests/viewer_fixture.py'), file],
    {cwd:root, env:{...process.env, PYTHONPATH:path.join(root, 'src')}});
  const accountsFile = path.join(output, 'accounts.html');
  const notesFile = path.join(output, 'notes.html');
  execFileSync(path.join(root, '.venv/bin/python'), ['-c',
    'import sys\nfrom pathlib import Path\nfrom viewer_fixture import write_note_fixture\nwrite_note_fixture(Path(sys.argv[1]))', notesFile],
    {cwd:root, env:{...process.env, PYTHONPATH:[path.join(root, 'src'),path.join(root, 'tests')].join(path.delimiter)}});
  execFileSync(path.join(root, '.venv/bin/python'), ['-c',
    'import sys\nfrom pathlib import Path\nfrom test_visualise import write_account_fixture\n'
    + 'from knot.visualise import main\nroot = Path(sys.argv[1])\nwrite_account_fixture(root)\n'
    + 'sys.argv = ["visualise", "--graph", str(root / "graph"), "--output", sys.argv[2]]\nmain()',
    path.join(output, 'accounts'), accountsFile],
    {cwd:root, env:{...process.env, PYTHONPATH:[path.join(root, 'src'),path.join(root, 'tests')].join(path.delimiter)}});
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const requests = [], errors = [];
  await context.route(/https?:\/\//, route => {requests.push(route.request().url()); return route.abort();});
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const claims = () => page.evaluate(() => edges.get().filter(e=>!e.organisation && !e.hidden).map(e=>e.id).sort());
  const themeLinks = () => page.evaluate(() => edges.get().filter(e=>e.organisation && !e.hidden).length);
  const facet = (name, value) => page.locator(`input[data-facet="${name}"][value="${value}"]`);
  const reset = () => page.locator('#reset-filters').click();
  const ready = () => page.waitForFunction(() => window.knotViewer
    && document.getElementById('layout-state').textContent === 'Layout paused', null, {timeout:60000});
  try {
    await page.goto(pathToFileURL(file).href); await ready();
    assert.equal(await page.locator('#animate-layout').count(), 1, 'Live layout control is available');
    assert.equal(await page.locator('#node-spacing').inputValue(), '150');
    assert.deepEqual(await claims(), ['ab','ac','bc','cd']);
    const evidenceBefore = await page.evaluate(() => edges.get().filter(e=>!e.organisation).map(e=>e.detail));
    const positions = await page.evaluate(() => network.getPositions(nodes.getIds()));
    const entityRow = await page.locator('.entity-choice').first().elementHandle();
    await page.locator('#theme-filters button').filter({hasText:/^None$/}).click();
    assert.equal(await entityRow.evaluate(n=>n.isConnected), true,
      'Filtering reuses entity controls instead of rebuilding the list');
    assert.deepEqual(await claims(), []);
    assert.equal(await page.locator('#empty-graph').isVisible(), true);
    await facet('themes','learning').check();
    assert.deepEqual(await claims(), ['ab','cd']);
    assert.equal(await page.locator('#empty-graph').isVisible(), false);
    assert.deepEqual(await page.evaluate(() => network.getPositions(nodes.getIds())), positions);
    // Overlapping theme checkboxes use OR, then intersect with other facets.
    await facet('themes','delivery').check();
    assert.deepEqual(await claims(), ['ab','bc','cd']);
    await facet('themes','__unthemed__').check();
    assert.deepEqual(await claims(), ['ab','ac','bc','cd']);
    await page.locator('summary').filter({hasText:/^Claims$/}).click();
    await facet('statuses','Unreviewed').uncheck();
    assert.deepEqual(await claims(), ['ab','ac','cd']);
    assert.equal(await themeLinks(), 0);
    assert.equal(await page.locator('#theme-links').isDisabled(), true);
    await facet('statuses','Unreviewed').check();
    await facet('origins','Inferred').uncheck();
    assert.deepEqual(await claims(), ['ab','ac','cd']);
    await reset();
    await page.locator('#kind-filter').selectOption('Question');
    assert.deepEqual(await claims(), ['bc','cd']);
    await reset();
    await page.locator('summary').filter({hasText:/^Node types$/}).click();
    await facet('types','Person').uncheck();
    assert.deepEqual(await claims(), ['bc','cd']);
    await reset();
    await page.locator('#entity-search').fill('Historical project heading');
    assert.equal(await page.locator('.entity-choice').count(), 1, 'Historical names are searchable');
    assert.equal(await page.locator('.entity-name').innerText(), 'Shared name');
    await page.locator('#entity-search').fill('Shared name');
    assert.equal(await page.locator('.entity-choice').count(), 2);
    const showC = page.locator('input[data-entity="c"]');
    await showC.focus(); await page.keyboard.press('Space');
    assert.equal(await showC.isChecked(), false);
    assert.equal(await showC.evaluate(n=>n===document.activeElement), true);
    assert.deepEqual(await claims(), ['ab']);
    await page.locator('#show-entities').click();
    assert.deepEqual(await claims(), ['ab','ac','bc','cd']);
    assert.equal(await page.locator('#hide-entities').innerText(), 'Hide non-matches');
    await page.locator('#hide-entities').click();
    assert.deepEqual(await claims(), ['bc']);
    await page.locator('#entity-search').fill('');
    assert.deepEqual(await page.locator('#entity-list input').evaluateAll(inputs=>
      inputs.filter(n=>n.checked).map(n=>n.dataset.entity).sort()), ['b','c']);
    await page.locator('#show-entities').click();
    assert.deepEqual(await claims(), ['ab','ac','bc','cd']);
    await page.locator('#entity-search').fill('does not exist');
    await page.locator('#hide-entities').click();
    assert.deepEqual(await claims(), []);
    await page.locator('#entity-search').fill('  Shared name  ');
    await page.locator('#hide-entities').click();
    assert.deepEqual(await claims(), ['bc'], 'A new search restores its matches even after hiding everything');
    await facet('statuses','Unreviewed').uncheck();
    assert.deepEqual(await claims(), [], 'Search isolation still respects the other filters');
    await page.locator('#hide-entities').click();
    assert.deepEqual(await claims(), []);
    await reset();
    await page.locator('#entity-search').fill(' ');
    await page.locator('#hide-entities').click();
    assert.deepEqual(await claims(), ['ab','ac','bc','cd'], 'An empty search matches all entities');
    assert.deepEqual(await page.evaluate(()=>network.getPositions(nodes.getIds())),positions);
    await page.locator('button[data-entity="b"]').click();
    const cards = page.locator('.curated-note');
    assert.equal(await cards.count(), 2);
    assert.deepEqual(await cards.evaluateAll(ns=>ns.map(n=>n.open)), [true,false]);
    assert.match(await cards.first().innerText(), /Recovery is planned\. Completion is not established\./);
    assert.match(await cards.first().innerText(), /Curated by Codex/);
    assert.equal(await page.locator('.note-sources').first().evaluate(n=>n.open), false);
    await page.locator('.note-sources > summary').first().click();
    assert.match(await cards.first().innerText(), /Please record that recovery remains planned\./);
    assert.match(await cards.first().innerText(), /No completed recovery established\./);
    assert.match(await cards.first().innerText(), /sources\/original.txt · line 1/);
    assert.equal(await page.locator('#selection-detail img, #selection-detail script').count(), 0);
    assert.equal(await page.evaluate(()=>window.injected), undefined);
    await cards.nth(1).locator(':scope > summary').click();
    await facet('statuses','Unreviewed').uncheck();
    assert.deepEqual(await cards.evaluateAll(ns=>ns.map(n=>n.open)), [true,true]);
    assert.equal(await page.locator('.note-sources').first().evaluate(n=>n.open), true);
    await facet('statuses','Unreviewed').check();
    await page.locator('button[data-entity="c"]').click();
    assert.equal(await cards.count(), 0, 'Shared display names never confer note associations');
    assert.match(await page.locator('#selection-detail').innerText(), /No note is associated/);
    // Canvas and list selection both open the same readable context.
    await page.evaluate(()=>{network.emit('click',{nodes:['b'],edges:[]});});
    assert.equal(await cards.count(), 2);
    assert.deepEqual(await cards.evaluateAll(ns=>ns.map(n=>n.open)), [true,false]);
    assert.deepEqual(await page.evaluate(()=>network.getPositions(nodes.getIds())),positions);
    assert.equal(await page.locator('.attribute').count(), 1);
    assert.equal(await page.evaluate(()=>nodes.get().some(n=>n.label==='18')), false);
    await page.locator('.attribute').click();
    assert.match(await page.locator('#selection-detail').innerText(), /Value \(literal\)\n18/);
    assert.match(await page.locator('#selection-detail').innerText(), /XMLSchema#integer/);
    assert.match(await page.locator('#selection-detail').innerText(), /Eighteen events were reported\./);
    await page.locator('button[data-entity="b"]').click();
    await page.locator('summary').filter({hasText:/^Entity details$/}).click();
    assert.match(await page.locator('#selection-detail').innerText(), /Historical project heading/);
    await page.getByRole('button', {name:'Focus on this entity', exact:true}).click();
    assert.deepEqual(await claims(), ['ab','bc']);
    assert.match(await page.locator('#focus-state').innerText(), /1 hop$/);
    assert.equal(await page.locator('#contract-focus').isDisabled(), true);
    await page.locator('#expand-focus').click();
    assert.deepEqual(await claims(), ['ab','ac','bc','cd']);
    assert.match(await page.locator('#focus-state').innerText(), /2 hops$/);
    assert.equal(await page.locator('#expand-focus').isDisabled(), true);
    await page.locator('#contract-focus').click();
    assert.deepEqual(await claims(), ['ab','bc']);
    assert.match(await page.locator('#focus-state').innerText(), /1 hop$/);
    assert.equal(await page.locator('#contract-focus').isDisabled(), true);
    await page.locator('#expand-focus').click();
    await page.locator('#reset-hops').click();
    assert.deepEqual(await claims(), ['ab','bc']);
    await page.locator('.connection').first().click();
    const detail = await page.locator('#selection-detail').innerText();
    assert.match(detail, /Exact quotation/);
    assert.match(detail, /<img src=x onerror="window.injected=true">/);
    assert.match(detail, /sources\/synthetic.txt/);
    assert.equal(await page.locator('#selection-detail img, #selection-detail script').count(), 0);
    assert.equal(await page.evaluate(()=>window.injected), undefined);
    await page.locator('#clear-focus').click();
    assert.deepEqual(await claims(), ['ab','ac','bc','cd']);
    await page.locator('#theme-links').uncheck(); assert.equal(await themeLinks(), 0);
    await page.locator('#edge-labels').uncheck();
    assert.equal(await page.evaluate(()=>edges.get().every(e=>e.label==='')), true);
    await reset();
    assert.equal(await page.evaluate(()=>edges.get().filter(e=>!e.organisation).every(e=>e.label==='relatedTo')), true);
    assert.deepEqual(await page.evaluate(() => edges.get().filter(e=>!e.organisation).map(e=>e.detail)), evidenceBefore);
    // Detail follows every camera path, including programmatic fit/focus, not only wheel events.
    const claimStyles = await page.evaluate(()=>edges.get().filter(e=>!e.organisation)
      .map(({id,dashes,color,label,width})=>({id,dashes,color,label,width})));
    const themeStyles = await page.evaluate(()=>edges.get().filter(e=>e.organisation)
      .map(({id,color,dashes})=>({id,color,dashes})));
    const camera = await page.evaluate(()=>({scale:network.getScale(),position:network.getViewPosition()}));
    await page.evaluate(()=>network.moveTo({scale:0.1,animation:false}));
    await page.waitForFunction(()=>edges.get().filter(e=>e.organisation).every(e=>e.dashes===false));
    assert.deepEqual(await page.evaluate(()=>network.getPositions(nodes.getIds())),positions);
    await page.locator('#theme-links').uncheck(); await page.locator('#theme-links').check();
    assert.equal(await page.evaluate(()=>edges.get().filter(e=>e.organisation).every(e=>e.dashes===false)),true);
    await page.evaluate(()=>network.moveTo({scale:0.3,animation:false}));
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    assert.equal(await page.evaluate(()=>edges.get().filter(e=>e.organisation).every(e=>e.dashes===false)),true,
      'A small zoom change inside the threshold band does not rebuild styles');
    await page.locator('button[data-entity="b"]').click();
    await page.waitForFunction(()=>edges.get().filter(e=>e.organisation).every(e=>Array.isArray(e.dashes)));
    assert.deepEqual(await page.evaluate(()=>edges.get().filter(e=>e.organisation)
      .map(({id,color,dashes})=>({id,color,dashes}))),themeStyles,'Close zoom restores the exact theme styling');
    assert.deepEqual(await page.evaluate(()=>edges.get().filter(e=>!e.organisation)
      .map(({id,dashes,color,label,width})=>({id,dashes,color,label,width}))),claimStyles,
      'Rendering detail never changes claim styling, including inferred dashes');
    await reset(); await page.evaluate(camera=>network.moveTo({...camera,animation:false}),camera);
    await page.locator('#layout-graph').click(); await ready();
    const geometry = () => page.evaluate(() => ({
      scale:network.getScale(), centre:network.getViewPosition(),
      meanLength:edges.get().filter(e=>!e.organisation && !e.hidden).reduce((sum,e) => {
        const a=network.getPosition(e.from), b=network.getPosition(e.to);
        return sum + Math.hypot(a.x-b.x,a.y-b.y);
      },0) / edges.get().filter(e=>!e.organisation && !e.hidden).length,
    }));
    const compact = await geometry();
    await page.locator('#node-spacing').evaluate(n => {
      n.value='300'; n.dispatchEvent(new Event('input', {bubbles:true}));
    });
    await ready();
    const spacious = await geometry();
    assert.ok(spacious.meanLength > compact.meanLength * 1.1, 'Spacing spreads connected nodes apart');
    assert.equal(spacious.scale, compact.scale, 'Spacing must preserve zoom');
    assert.deepEqual(spacious.centre, compact.centre, 'Spacing must preserve the camera centre');
    assert.equal(await page.locator('#spacing-value').innerText(), '3×');
    await page.evaluate(() => {
      const p=network.getPosition('a'); network.moveNode('a',p.x+180,p.y);
      window.layoutStart=network.getPosition('a');
    });
    await page.locator('#animate-layout').check();
    await page.waitForFunction(() => Math.abs(network.getPosition('a').x-layoutStart.x)>1);
    await facet('themes','delivery').uncheck();
    assert.equal(await page.locator('#animate-layout').isChecked(), true);
    assert.equal(await page.evaluate(()=>network.physics.options.enabled), true);
    assert.deepEqual(await claims(), ['ab','ac','cd']);
    await page.locator('#theme-filters button').filter({hasText:/^None$/}).click();
    assert.deepEqual(await claims(), []);
    assert.equal(await page.locator('#animate-layout').isChecked(), true);
    assert.equal(await page.evaluate(()=>network.physics.options.enabled), false);
    await facet('themes','learning').check();
    await facet('themes','__unthemed__').check();
    assert.equal(await page.evaluate(()=>network.physics.options.enabled), true);
    assert.deepEqual(await claims(), ['ab','ac','cd']);
    await page.locator('input[data-entity="d"]').uncheck();
    const hiddenPosition = await page.evaluate(()=>network.getPosition('d'));
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.deepEqual(await page.evaluate(()=>network.getPosition('d')),hiddenPosition);
    await page.locator('#pause-layout').click(); await ready();
    assert.equal(await page.locator('#animate-layout').isChecked(), false);
    const paused = await page.evaluate(()=>network.getPositions(nodes.getIds()));
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.deepEqual(await page.evaluate(()=>network.getPositions(nodes.getIds())),paused);
    await page.locator('#animate-layout').check();
    await page.locator('#animate-layout').uncheck(); await ready();
    await reset();
    assert.equal(await page.locator('#node-spacing').inputValue(),'300', 'Filter reset preserves layout preferences');
    assert.deepEqual(await page.evaluate(() => edges.get().filter(e=>!e.organisation).map(e=>e.detail)), evidenceBefore);
    await page.locator('#fit-graph').click();
    await page.screenshot({path:path.join(output,'desktop.png'), fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), true);
    assert.ok(await page.locator('canvas').evaluate(n=>n.getBoundingClientRect().height)>=320);
    await page.screenshot({path:path.join(output,'mobile.png'), fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(pathToFileURL(accountsFile).href); await ready();
    assert.deepEqual(await claims(), ['urn:assertion:first','urn:assertion:retelling'],
      'Account qualifications preserve distinct assertion occurrences');
    assert.equal(await page.evaluate(()=>nodes.length), 2, 'A literal count remains an attribute');
    const accountsBefore = await page.evaluate(()=>edges.get().map(e=>e.detail));
    await page.evaluate(()=>network.emit('click',{nodes:[],edges:['urn:assertion:first']}));
    const accountDetail = await page.locator('#selection-detail').innerText();
    assert.match(accountDetail, /Repeated source account\nA retelling is not independent corroboration\./);
    assert.match(accountDetail, /Unresolved source overlap\nEvents and pipelines may overlap; do not add their counts\./);
    assert.match(accountDetail, /Account qualification by\nReviewer <\/script><script>window.accountInjected=true<\/script>/);
    assert.match(accountDetail, /<img src=x onerror="window.accountInjected=true">/);
    assert.match(accountDetail, /Accepted · Explicit/);
    assert.match(accountDetail, /Exact quotation\nAlex reported 18 events in the Orion rollout\./);
    assert.equal(await page.locator('#selection-detail img, #selection-detail script').count(), 0);
    assert.equal(await page.evaluate(()=>window.accountInjected), undefined);
    await page.locator('button[data-entity="urn:outcome:orion"]').click();
    await page.locator('.attribute').click();
    const countDetail = await page.locator('#selection-detail').innerText();
    assert.match(countDetail, /Value \(literal\)\n18/);
    assert.match(countDetail, /Unreviewed · Explicit/);
    assert.match(countDetail, /Unresolved source overlap\nEvents and pipelines may overlap; do not add their counts\./);
    assert.match(countDetail, /18 pipelines were reported; overlap with Orion events is unresolved\./);
    assert.doesNotMatch(countDetail, /Repeated source account/);
    await reset();
    assert.deepEqual(await page.evaluate(()=>edges.get().map(e=>e.detail)), accountsBefore,
      'Filtering does not alter account qualifications or original evidence');
    await page.screenshot({path:path.join(output,'account-qualifications.png'),fullPage:true});
    await page.goto(pathToFileURL(notesFile).href); await ready();
    assert.equal(await page.evaluate(()=>nodes.get().filter(n=>n.role==='note' && !n.hidden).length), 3);
    assert.equal(await page.evaluate(()=>edges.get().filter(e=>e.navigation && !e.hidden).length), 2);
    await page.locator('#entity-search').fill('AI reflection');
    await page.locator('.entity-name').click();
    assert.match(await page.locator('#selection-detail').innerText(), /Small modules help me review AI coding/);
    assert.equal(await page.locator('#selection-detail script').count(), 0);
    assert.equal(await page.evaluate(()=>window.injected), undefined);
    await page.getByRole('button', {name:'Focus on this note',exact:true}).click();
    const citizen = 'urn:knot:entity:00000000-0000-4000-8000-000000000001';
    assert.equal(await page.evaluate(id=>nodes.get(id).hidden, citizen), true);
    await page.locator('#expand-focus').click();
    assert.equal(await page.evaluate(id=>nodes.get(id).hidden, citizen), false);
    assert.equal(await page.locator('#expand-focus').isDisabled(), true);
    await page.locator('#reset-hops').click();
    assert.equal(await page.evaluate(id=>nodes.get(id).hidden, citizen), true);
    await page.locator('#clear-focus').click();
    await page.locator('.connection').click();
    assert.match(await page.locator('#selection-detail').innerText(), /Suggests practical foundations, not proof/);
    await page.getByRole('button', {name:'Explore linked subject',exact:true}).click();
    assert.match(await page.locator('#selection-detail h3').innerText(), /Citizen developer foundations/);
    assert.equal(await page.locator('.connection').count(), 2);
    await page.locator('.connection').filter({hasText:'→ about →'}).click();
    await page.getByRole('button', {name:'Explore linked subject',exact:true}).click();
    assert.equal(await page.locator('.connection').count(), 1);
    await page.locator('#note-links').uncheck();
    assert.equal(await page.evaluate(()=>nodes.get().filter(n=>!n.hidden).length), 0);
    await reset();
    await page.locator('#entity-search').fill('Unlinked thought');
    await page.locator('.entity-name').click();
    assert.match(await page.locator('#selection-detail').innerText(), /An idea without links/);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), true);
    await page.screenshot({path:path.join(output,'notes-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    const customTheme = path.join(output, 'custom-theme.json');
    await fs.writeFile(customTheme, JSON.stringify({schema_version:1, name:'Custom',
      colors:{background:'#101020', entity:'#556677', accepted:'#ffcc44'},
      fonts:{ui:'serif',graph:'serif'}}));
    const customCss = path.join(output, 'ocean.css');
    await fs.writeFile(customCss, ':root { --background: #152634; --entity: #66bbcc; --accepted: #aacc66; --font-graph: serif; }');
    for (const style of [
      {name:'paper',theme:'paper',background:'rgb(250, 248, 243)',entity:'#81acb9',accepted:'#237149'},
      {name:'midnight',theme:'midnight',background:'rgb(17, 24, 39)',entity:'#3b82f6',accepted:'#34d399'},
      {name:'custom',theme:customTheme,background:'rgb(16, 16, 32)',entity:'#556677',accepted:'#ffcc44'},
      {name:'custom-css',theme:customCss,background:'rgb(21, 38, 52)',entity:'#66bbcc',accepted:'#aacc66'},
    ]) {
      const themedFile = path.join(output, style.name + '.html');
      execFileSync(path.join(root, '.venv/bin/python'), ['-c',
        'import sys\nfrom pathlib import Path\nfrom viewer_fixture import write_fixture\n'
        + 'write_fixture(Path(sys.argv[1]), visual_theme=sys.argv[2])', themedFile, style.theme],
        {cwd:root,env:{...process.env,PYTHONPATH:[path.join(root,'src'),path.join(root,'tests')].join(path.delimiter)}});
      await page.goto(pathToFileURL(themedFile).href); await ready();
      assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor), style.background);
      assert.equal(await page.evaluate(()=>nodes.get('a').color.background), style.entity);
      assert.equal(await page.evaluate(()=>edges.get('ab').color), style.accepted);
      assert.deepEqual(await page.evaluate(()=>edges.get().filter(e=>!e.organisation).map(e=>e.detail)), evidenceBefore);
      await page.screenshot({path:path.join(output,style.name+'-desktop.png'),fullPage:true});
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), true);
      await page.screenshot({path:path.join(output,style.name+'-mobile.png'),fullPage:true});
      await page.setViewportSize({width:1440,height:1000});
    }
    if (process.argv[2]) {
      await page.goto(pathToFileURL(path.resolve(process.argv[2])).href); await ready();
      const before = await page.evaluate(()=>({nodes:nodes.length,edges:edges.length,positions:network.getPositions(nodes.getIds())}));
      const toggle = page.locator('#theme-filters input').first();
      if (await toggle.count()) {
        await toggle.click(); await toggle.click();
        assert.deepEqual(await page.evaluate(()=>network.getPositions(nodes.getIds())),before.positions);
        assert.deepEqual(await page.evaluate(()=>({nodes:nodes.length,edges:edges.length})), {nodes:before.nodes,edges:before.edges});
      }
      assert.equal(await page.locator('#mynetwork').isVisible(), true);
      await page.screenshot({path:path.join(output,'supplied-snapshot.png'),fullPage:true});
      console.log(JSON.stringify({snapshot_nodes:before.nodes,snapshot_edges:before.edges}));
    }
    assert.deepEqual(requests, []); assert.deepEqual(errors, []);
    console.log('Browser interaction checks passed; screenshots: '+output);
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
