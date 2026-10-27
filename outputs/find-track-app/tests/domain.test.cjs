const assert = require('node:assert/strict');
const {test} = require('node:test');
const {score, canonicalPosting, mergeRecords, suggestRequirements, acceptanceTask, advanceWorkflow} = require('../static/domain.js');
test('coverage uses reviewed weighted evidence, not known but omitted terms', () => {
  const job={jd:'Required Node.js; preferred CI/CD',jdVerified:true,requirements:[{term:'Node.js',weight:2,coverage:'full',evidence:'Built Node.js APIs'},{term:'CI/CD',weight:1,coverage:'known',evidence:'User confirms basics'}]};
  assert.equal(score(job),67);
  job.requirements[0].coverage='partial'; assert.equal(score(job),33);
  job.requirements[0].coverage='unreviewed'; assert.equal(score(job),null);
});
test('empty JD, unchecked JD or missing resume evidence never produces a score', () => {
  const job={jd:'Node.js',jdVerified:true,requirements:[{term:'Node.js',weight:2,coverage:'full',evidence:''}]};
  assert.equal(score(job),null);
  job.requirements[0].evidence='Node.js'; job.jd=''; assert.equal(score(job),null);
  job.jd='Node.js'; job.jdVerified=false; assert.equal(score(job),null);
});
test('posting deduplication removes tracking but preserves distinct query requisitions', () => {
  assert.equal(canonicalPosting('https://in.linkedin.com/jobs/view/123?utm_source=x'),canonicalPosting('https://www.linkedin.com/jobs/view/123/'));
  assert.notEqual(canonicalPosting('https://example.com/careers?id=1'),canonicalPosting('https://example.com/careers?id=2'));
});
test('research merge is idempotent and cannot regress an existing application', () => {
  const state={profile:{name:'User'},rules:[],jobs:[{id:'j',status:'interview'}],contacts:[],actions:[],events:[],companies:[]};
  const incoming={...structuredClone(state),jobs:[{id:'j',status:'saved'},{id:'new',status:'saved'}]};
  const result=mergeRecords(state,incoming);
  assert.equal(result.jobs[0].status,'interview'); assert.equal(result.jobs.length,2);
  assert.deepEqual(mergeRecords(result,incoming),result); assert.equal(state.jobs.length,1);
});
test('skill suggestions use lexical boundaries and always require review', () => {
  const result=suggestRequirements('JavaScript and CI/CD are preferred.','Languages: JavaScript',[]);
  assert.ok(result.some(r=>r.term==='JavaScript')); assert.ok(!result.some(r=>r.term==='Java'));
  assert.ok(result.every(r=>r.coverage==='unreviewed'));
  assert.equal(suggestRequirements('Node.js','Node.js',[{term:'Node.js'}]).length,0);
});
test('confirmed acceptance creates exactly one follow-up; other states do not', () => {
  const data={actions:[]};
  const person={id:'test-person',name:'Test Person',jobIds:['test-job'],status:'request sent'};
  acceptanceTask(data,person,()=> 'a1'); assert.equal(data.actions.length,0);
  person.status='accepted'; acceptanceTask(data,person,()=> 'a1');
  acceptanceTask(data,person,()=> 'a2'); assert.equal(data.actions.length,1);
  assert.equal(data.actions[0].jobId,'test-job');
  assert.equal(data.actions[0].status,'pending');
});
test('one-tap transitions finish old work and prepare one truthful follow-up', () => {
  const data={profile:{name:'Test User',candidate:{graduationYear:2026,degreeLabel:'B.Tech CSE'}},jobs:[{id:'j',title:'Engineer',company:'Example',status:'applied',preparation:{matches:[{term:'Node.js'}]}}],contacts:[],actions:[{id:'apply',jobId:'j',kind:'apply',status:'pending'}]};
  let id=0;
  const advance=()=>advanceWorkflow(data,()=>String(++id),'2026-10-27');
  advance(); advance();
  assert.equal(data.actions[0].status,'done');
  assert.equal(data.actions.filter(a=>a.kind==='recruiter research').length,1);
  data.contacts.push({id:'p',name:'Recruiter Person',jobIds:['j'],status:'accepted'});
  advance(); advance();
  assert.equal(data.actions.find(a=>a.kind==='recruiter research').status,'done');
  assert.equal(data.actions.filter(a=>a.kind==='acceptance').length,1);
  assert.match(data.contacts[0].draft,/I applied for/);
  assert.match(data.contacts[0].draft,/Node.js/);
  data.contacts[0].draft='My reviewed message'; advance();
  assert.equal(data.contacts[0].draft,'My reviewed message');
  data.contacts[0].status='message sent'; advance();
  assert.equal(data.actions.find(a=>a.kind==='acceptance').status,'done');
});
