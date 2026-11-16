// Run the installed English and Simplified Chinese OCR models.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const bundledModules = path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime',
  'dependencies', 'node', 'node_modules');
const modules = process.env.ART_NODE_MODULES || bundledModules;
const enginePath = path.join(modules, 'tesseract.js');
const { createWorker, PSM } = require(enginePath);
const { version } = require(path.join(enginePath, 'package.json'));
const engine = `tesseract.js-${version}-eng+chi_sim`;
const cachePath = process.env.ART_OCR_CACHE || (process.platform === 'win32' ?
  'D:/gunforge_cache/ocr' : path.join(os.tmpdir(), 'gunforge-ocr'));

async function recognize(worker, file) {
  const { data } = await worker.recognize(file, {}, { blocks: true });
  const words = (data.blocks || []).flatMap(block => block.paragraphs.flatMap(paragraph =>
    paragraph.lines.flatMap(line => line.words.map(({ text, confidence, bbox }) => ({ text, confidence, bbox })))));
  return { text: data.text, confidence: data.confidence, words, engine };
}

async function batch(requestPath, count) {
  const requests = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
  const layouts = { sparse: PSM.SPARSE_TEXT, line: PSM.SINGLE_LINE, auto: PSM.AUTO };
  let next = 0;
  const jobs = Array.from({ length: count }, async () => {
    const worker = await createWorker('eng+chi_sim', 1, { cachePath });
    try {
      let layout = '';
      while (next < requests.length) {
        const request = requests[next++];
        if (!Object.hasOwn(layouts, request.layout)) {
          throw new Error(`Unsupported OCR layout: ${request.layout}`);
        }
        if (request.layout !== layout) {
          layout = request.layout;
          await worker.setParameters({ tessedit_pageseg_mode: layouts[layout] });
        }
        const result = await recognize(worker, path.resolve(path.dirname(requestPath), request.file));
        process.stdout.write(JSON.stringify({ id: request.id, ...result }) + '\n');
      }
    } finally {
      await worker.terminate();
    }
  });
  const outcomes = await Promise.allSettled(jobs);
  for (const outcome of outcomes) {
    if (outcome.status === 'rejected') {
      throw outcome.reason;
    }
  }
}

async function main() {
  fs.mkdirSync(cachePath, { recursive: true });
  if (process.argv[2] === '--batch') {
    const count = Number(process.argv[4] || 1);
    if (!Number.isInteger(count) || count < 1 || count > 4) {
      throw new Error('OCR batch worker count must be between 1 and 4');
    }
    await batch(process.argv[3], count);
    return;
  }
  const worker = await createWorker('eng+chi_sim', 1, { cachePath });
  try {
    process.stdout.write(JSON.stringify(await recognize(worker, process.argv[2])));
  } finally {
    await worker.terminate();
  }
}

main().catch(error => {
  process.stderr.write(String(error) + '\n');
  process.exitCode = 1;
});
