(function (root) {
  'use strict';
  function score(job) {
    const rows = job.requirements || [];
    if (!job.jdVerified || !job.jd?.trim() || !rows.length || rows.some(r => r.coverage === 'unreviewed') || rows.some(r => ['full', 'partial'].includes(r.coverage) && !r.evidence?.trim())) return null;
    const total = rows.reduce((sum, r) => sum + r.weight, 0);
    return Math.round(rows.reduce((sum, r) => sum + r.weight * (r.coverage === 'full' ? 1 : r.coverage === 'partial' ? 0.5 : 0), 0) / total * 100);
  }
  function canonicalPosting(url) {
    const parsed = new URL(url);
    if (parsed.hostname.endsWith('.linkedin.com')) parsed.hostname = 'linkedin.com';
    parsed.hash = '';
    parsed.pathname = parsed.pathname.replace(/\/$/, '');
    for (const key of [...parsed.searchParams.keys()]) {
      if (/^(utm_|trk$|trackingId$|refId$|gh_src$|source$)/i.test(key)) parsed.searchParams.delete(key);
    }
    parsed.searchParams.sort();
    return parsed.href;
  }
  function mergeRecords(current, incoming) {
    const result = structuredClone(current);
    for (const key of ['jobs', 'contacts', 'actions', 'events', 'companies']) {
      const ids = new Set(result[key].map(x => x.id));
      for (const row of incoming[key]) {
        if (!ids.has(row.id)) {
          result[key].push(structuredClone(row));
          ids.add(row.id);
        }
      }
    }
    return result;
  }
  function acceptanceTask(data, person, makeId) {
    if (person.status !== 'accepted' || data.actions.some(a => a.contactId === person.id && a.kind === 'acceptance')) return;
    data.actions.push({id: makeId(), title: `Prepare follow-up for ${person.name}`, details: 'Review the relevant role, tailor your message and attach the chosen resume manually.', jobId: person.jobIds[0] || '', contactId: person.id, kind: 'acceptance', status: 'pending'});
  }
  function createMessage(person, job, profile, connected = false) {
    if (!job) return '';
    const first = person.name.split(' ')[0];
    const facts = profile.candidate || {};
    const intro = facts.graduationYear && facts.degreeLabel ? `I’m a ${facts.graduationYear} ${facts.degreeLabel} graduate.` : 'I’m interested in software development opportunities.';
    const applied = ['applied','assessment','interview','offer'].includes(job.status);
    const terms = (job.preparation?.matches || []).map(x=>x.term).filter(x=>!['Git','DSA','OOP'].includes(x)).slice(0,3);
    return `Hi ${first}, ${connected ? 'thanks for connecting. ' : ''}${intro} ${applied ? 'I applied for' : 'I’m interested in'} the ${job.title} role at ${job.company}. ${terms.length ? 'My resume includes '+terms.join(', ')+'. ' : ''}Would you be the right person to contact about this role, or could you point me to the relevant recruiter? Thank you, ${profile.name.split(' ')[0]}.`;
  }
  function advanceWorkflow(data, makeId, at) {
    for (const job of data.jobs) {
      const submitted = !['saved','selected'].includes(job.status);
      for (const action of data.actions) {
        if (action.jobId===job.id && submitted && (action.kind==='apply' || action.id==='A-CG-APPLY')) action.status='done';
      }
      if (job.status==='applied' && !data.contacts.some(p=>(p.jobIds||[]).includes(job.id)) && !data.actions.some(a=>a.kind==='recruiter research'&&a.jobId===job.id)) {
        data.actions.push({id:makeId(),jobId:job.id,kind:'recruiter research',title:'Recruiter research: '+job.company,details:'Queued for assistant research. No background recruiter search is active.',status:'pending'});
      }
    }
    for (const person of data.contacts) {
      const job=data.jobs.find(j=>(person.jobIds||[]).includes(j.id));
      if (!job) continue;
      if (['accepted','message prepared'].includes(person.status)) {
        acceptanceTask(data,person,makeId);
        if (!person.draft) {person.draft=createMessage(person,job,data.profile,true);person.draftPreparedAt=at;}
        const task=data.actions.find(a=>a.contactId===person.id&&a.kind==='acceptance');
        if (task && task.status!=='done') {task.title='Review message for '+person.name;task.details='Your message is ready. Review, copy and send manually with your chosen resume.';}
      }
      for (const task of data.actions) {
        if (task.contactId===person.id&&task.kind==='acceptance'&&['message sent','replied','do not contact'].includes(person.status)) task.status='done';
        if (task.kind==='recruiter research'&&task.jobId===job.id) task.status='done';
      }
    }
  }
  const skillPatterns = [
    ['JavaScript', /\bjavascript\b/i], ['TypeScript', /\btypescript\b/i],
    ['Node.js', /\bnode(?:\.js|js)?\b/i], ['Express', /\bexpress(?:\.js|js)?\b/i],
    ['React', /\breact(?:\.js|js)?\b/i], ['Python', /\bpython\b/i], ['Java', /\bjava\b/i],
    ['REST APIs', /\brest(?:ful)?\b/i], ['SQL', /\b(?:sql|mysql|postgresql)\b/i],
    ['MongoDB', /\bmongodb\b/i], ['Docker', /\bdocker\b/i], ['AWS', /\baws\b/i],
    ['Linux', /\blinux\b/i], ['Git', /\bgit\b/i], ['CI/CD', /\bci\s*[\/-]\s*cd\b|continuous integration|continuous delivery|continuous deployment/i],
    ['DevOps', /\bdevops\b/i], ['Testing', /\btesting\b|unit tests?|api tests?/i],
    ['HTML', /\bhtml5?\b/i], ['CSS', /\bcss3?\b/i], ['Tailwind CSS', /\btailwind\b/i],
    ['FastAPI', /\bfastapi\b/i], ['Data structures & algorithms', /\bdata structures\b|\bdsa\b/i],
    ['Kubernetes', /\bkubernetes\b|\bk8s\b/i], ['Redis', /\bredis\b/i]
  ];
  function suggestRequirements(jd, resume, existing) {
    const known = new Set(existing.map(r => r.term.toLowerCase()));
    return skillPatterns.filter(([term, regex]) => regex.test(jd) && !known.has(term.toLowerCase())).map(([term, regex]) => {
      const line = resume.split('\n').find(text => regex.test(text));
      return {term, weight: 2, coverage: 'unreviewed', evidence: line ? 'Candidate evidence — review: ' + line.trim() : ''};
    });
  }
  const api = {score, canonicalPosting, mergeRecords, suggestRequirements, acceptanceTask, createMessage, advanceWorkflow};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FindTrack = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
