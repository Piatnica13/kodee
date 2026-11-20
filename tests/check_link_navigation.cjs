// Exercise the real delegated navigation handler without a browser or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/static/js/navigation.js', 'utf8');
let checks = 0;
function run(overrides = {}, linkOverrides = {}, reducedMotion = false) {
  const location = {href:'http://localhost/shop', origin:'http://localhost',
    pathname:'/shop', search:''};
  const actions = [];
  location.assign = href => { location.href = href; };
  let click;
  const context = {URL,
    window: {location, matchMedia: () => ({matches: reducedMotion}), addEventListener() {}},
    document: {
      addEventListener: (_, listener) => { click = listener; },
      body: {classList: {add: () => actions.push('fade')}},
    },
    setTimeout: callback => { callback(); return 1; },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const link = {href:'http://localhost/product/samolet', target:'',
    hasAttribute:()=>false, ...linkOverrides};
  const event = {target:{closest:()=>link}, button:0, defaultPrevented:false,
    preventDefault:()=>actions.push('prevent'), ...overrides};
  click(event);
  checks++;
  return {actions, location};
}
assert.deepEqual(run().actions, ['prevent','fade']);
assert.equal(run().location.href, 'http://localhost/product/samolet');
for (const key of ['ctrlKey','metaKey','shiftKey','altKey','defaultPrevented']) {
  assert.deepEqual(run({[key]:true}).actions, [], key);
}
assert.deepEqual(run({button:1}).actions, []);
for (const target of ['_blank','comparison']) {
  assert.deepEqual(run({}, {target}).actions, []);
}
assert.deepEqual(run({}, {hasAttribute:name=>name==='download'}).actions, []);
for (const href of ['tel:77003360024','mailto:shop@example.com',
  'https://wa.me/77003360024','http://localhost/shop#productGrid']) {
  assert.deepEqual(run({}, {href}).actions, [], href);
}
assert.deepEqual(run({}, {target:'_self'}).actions, ['prevent','fade']);
assert.deepEqual(run({target:{closest:()=>null}}).actions, []);
assert.deepEqual(run({}, {hasAttribute:name=>name==='data-instant-navigation'}).actions, []);
assert.deepEqual(run({}, {}, true).actions, []);
console.log(`Navigation handler: ${checks} scenarios passed`);
