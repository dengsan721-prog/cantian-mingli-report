const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

async function main() {
  const url = process.env.PREVIEW_URL || 'http://127.0.0.1:8822';
  const out = path.resolve(process.env.PREVIEW_OUTPUT || path.join(__dirname, '../../mingli-system/evaluations/runtime-preview-v62'));
  const expectedVersion = process.env.EXPECTED_MODEL_VERSION || 'wisdom-report-v86';
  await fs.mkdir(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    const context = await browser.newContext();
    const cases = [
      { name: '叙事验收示例', gender: 'male', year: 1993, month: 7, day: 16, timeText: '09:30' },
      { name: '成长验收示例', gender: 'female', year: 2016, month: 10, day: 3, timeText: '' },
      { name: '幼儿照护验收示例', gender: 'male', year: 2024, month: 6, day: 8, timeText: '' },
      { name: '青春期验收示例', gender: 'female', year: 2010, month: 6, day: 9, timeText: '' },
    ];
    const records = [];
    for (const item of cases) {
      const payload = { ...item, calendarType: 'solar', birthplace: '西安', timezone: 'Asia/Shanghai', calendarVerified: true, timeStandardVerified: true, events: [] };
      const response = await context.request.post(`${url}/api/reports`, { data: payload });
      assert.equal(response.status(), 201, await response.text());
      const record = await response.json();
      assert.equal(record.report.modelVersion, expectedVersion);
      assert.equal(record.report.narrativeProfile.referenceDate, '2026-09-20');
      const repeated = await (await context.request.post(`${url}/api/reports`, { data: payload })).json();
      assert.equal(record.recordId, repeated.recordId);
      assert.equal(repeated.reused, true);
      records.push(record);
    }
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.setViewportSize(viewport);
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.screenshot({ path: path.join(out, `form-${viewport.width}.png`) });
      for (const record of records) {
        if (viewport.width < 600) await page.locator('#historyToggle').click();
        await page.locator(`[data-record-id="${record.recordId}"] .history-item-open`).click();
        await page.waitForFunction(name => document.querySelector('#reportHero')?.textContent.includes(name), record.input.name);
        if (viewport.width < 600) {
          await page.waitForFunction(() => document.querySelector('#historySidebar').getBoundingClientRect().right <= 1);
        }
        assert.equal(await page.getByText('阶段参照 2026-09-20', { exact: true }).isVisible(), true);
        await page.locator('#report-portrait').waitFor();
        await page.getByRole('tab', { name: '精读', exact: true }).click();
        for (const section of record.report.sections) {
          const chapter = page.locator(`#report-${section.id}`);
          if (section.narrativeLayout === 'linked_actions') {
            assert.equal(await chapter.locator('.report-summary, .deep-insight').count(), 0);
            assert.equal(await chapter.locator('.report-list-title').innerText(), section.listTitle);
            const links = chapter.locator('li a');
            assert.equal(await links.count(), section.items.length);
            for (let i = 0; i < section.items.length; i++) {
              assert.equal(await links.nth(i).isVisible(), true);
              assert.equal(await chapter.locator('li').nth(i).innerText(), `${section.items[i]} 回看前文`);
              const target = `#report-${section.narrativeEvidence.linkedActions[i].sectionId}`;
              assert.equal(await links.nth(i).getAttribute('href'), target);
              await links.nth(i).click();
              assert.equal(new URL(page.url()).hash, target);
              assert.equal(await page.locator(target).isVisible(), true);
            }
            await page.getByRole('tab', { name: '精读', exact: true }).click();
            continue;
          }
          const arcs = chapter.locator('.report-arc');
          assert.equal(await arcs.count(), 2);
          assert.equal(await arcs.nth(0).isVisible(), true);
          assert.equal(await arcs.nth(0).locator('.report-story p').nth(1).isVisible(), true);
          const firstArc = (section.narrativeArcOrder || [0, 1])[0];
          assert.equal(await arcs.nth(0).locator('.report-arc-reflection').innerText(), [section.summary, section.insight][firstArc]);
          assert.equal(await arcs.nth(0).locator('.report-arc-action').innerText(), `试一步${section.items[firstArc]}`);
          assert.equal(await arcs.nth(1).isVisible(), false);
        }
        await page.getByRole('tab', { name: '全文', exact: true }).click();
        for (const section of record.report.sections) {
          if (section.narrativeLayout === 'linked_actions') {
            assert.equal(await page.locator(`#report-${section.id} li a`).count(), 3);
            continue;
          }
          const arcs = page.locator(`#report-${section.id} .report-arc`);
          for (let i = 0; i < 2; i++) {
            const source = (section.narrativeArcOrder || [0, 1])[i];
            assert.equal(await arcs.nth(i).isVisible(), true);
            assert.deepEqual(await arcs.nth(i).locator('.report-story p').allTextContents(), section.scenes.slice(source * 2, source * 2 + 2));
            assert.equal(await arcs.nth(i).locator('.report-arc-reflection').innerText(), [section.summary, section.insight][source]);
            assert.equal(await arcs.nth(i).locator('.report-arc-action').innerText(), `试一步${section.items[source]}`);
          }
        }
        const band = record.report.sections[0].narrativeEvidence.selectionBasis.developmentalBand || record.report.narrativeProfile.audience;
        const prefix = `${band}-${viewport.width}`;
        await fs.writeFile(path.join(out, `${prefix}.txt`), await page.locator('.report-content').innerText(), 'utf8');
        const layout = await page.evaluate(async () => {
          const pictures = [...document.querySelectorAll('.section-illustration img')];
          await Promise.all(pictures.map(image => { image.loading = 'eager'; return image.decode(); }));
          return { viewport: window.innerWidth, document: document.documentElement.scrollWidth,
            sidebarRight: document.querySelector('#historySidebar').getBoundingClientRect().right,
            sections: document.querySelectorAll('.report-section').length,
            imageCount: pictures.length, uniqueImages: new Set(pictures.map(image => image.src)).size,
            brokenImages: pictures.filter(image => !image.naturalWidth).length,
            clippedImages: pictures.filter(image => image.parentElement.classList.contains('section-illustration-viewport') && getComputedStyle(image.parentElement).overflow === 'hidden').length,
            overlappingCaptions: pictures.filter(image => image.closest('figure').querySelector('figcaption').getBoundingClientRect().top < image.parentElement.getBoundingClientRect().bottom - 1).length };
        });
        assert.ok(layout.document <= viewport.width + 1, JSON.stringify(layout));
        if (viewport.width < 600) assert.ok(layout.sidebarRight <= 1, JSON.stringify(layout));
        assert.equal(layout.sections, 10);
        assert.equal(layout.brokenImages, 0);
        assert.equal(layout.uniqueImages, layout.imageCount);
        assert.equal(layout.clippedImages, layout.imageCount);
        assert.equal(layout.overlappingCaptions, 0);
        await page.locator('#report-portrait').scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(out, `${prefix}-portrait.png`) });
        if (band === 'adult') {
          for (const section of ['wellbeing', 'review', 'relationships', 'turning-points', 'actions', 'career', 'structure', 'character', 'wealth']) {
            await page.locator(`#report-${section}`).scrollIntoViewIfNeeded();
            await page.screenshot({ path: path.join(out, `${prefix}-${section}.png`) });
          }
        }
        results.push({ audience: record.report.narrativeProfile.audience, developmentalBand: band, modelVersion: record.report.modelVersion, viewport, layout, errors: [...errors] });
        assert.deepEqual(errors, []);
      }
      await page.close();
    }
    await context.close();
  } finally {
    await browser.close();
  }
  await fs.writeFile(path.join(out, 'smoke.json'), JSON.stringify(results, null, 2));
  const files = {};
  for (const file of ['app.js', 'styles.css', 'scripts/smoke_wisdom.cjs']) {
    files[file] = crypto.createHash('sha256').update(await fs.readFile(path.resolve(__dirname, '..', file))).digest('hex');
  }
  await fs.writeFile(path.join(out, 'ui-verification.json'), JSON.stringify({ checkedAt: new Date().toISOString(), url, files, results }, null, 2));
  console.log(JSON.stringify(results, null, 2));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
