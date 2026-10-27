const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
test('application boot and every screen render with the domain bundle loaded', async () => {
  const app = {innerHTML:''};
  const modal = {};
  const sample = {schema:1,profile:{name:'Test User',resume:'Node.js'},jobs:[{id:'j1',company:'Example',title:'Software Engineer',status:'saved',screening:'review',location:'India',type:'Full-time',skills:[],requirements:[]}],contacts:[{id:'p1',name:'Test Recruiter',company:'Example',status:'discovered',role:'Recruiter',jobIds:['j1']}],companies:[],actions:[],events:[],rules:[]};
  const context=vm.createContext({console,structuredClone,URL,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,document:{querySelector:s=>s==='#app'?app:s==='#modal'?modal:{},addEventListener:()=>{}},fetch:async url=>({ok:true,json:async()=>url==='/api/session'?{token:'test'}:{revision:1,data:sample}})});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/domain.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(app.innerHTML.includes('Your next opportunity.'));
  for (const page of ['shortlist','applications','people','followups','discover','profile','detail']) {
    vm.runInContext(`page=${JSON.stringify(page)};selected='j1';render();`,context);
    assert.ok(app.innerHTML.includes('find&track'),page);
    assert.ok(!app.innerHTML.includes('undefined'),page);
  }
  for (const tab of ['overview','resume','people','activity']) {
    vm.runInContext(`page='detail';tab=${JSON.stringify(tab)};render();`,context);
    assert.ok(app.innerHTML.includes('Software Engineer'),tab);
  }
});
