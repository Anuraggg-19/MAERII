const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('app/static/app.js', 'utf8');
const context = {
  document: {
    addEventListener() {},
    getElementById() { return null; },
    querySelectorAll() { return []; },
  },
  localStorage: { getItem() { return null; }, setItem() {} },
  console,
};

vm.createContext(context);
vm.runInContext(source, context);
const testScript = [
  "recommendationCache = { '4:first': { id: 1 }, '4:second': { id: 2 }, '5:other': { id: 3 } };",
  'invalidateRecommendationCache(4);',
  'JSON.stringify(recommendationCache);',
].join('\n');
const result = vm.runInContext(testScript, context);

assert.deepEqual(JSON.parse(result), { '5:other': { id: 3 } });
console.log('recommendation cache invalidation: ok');
