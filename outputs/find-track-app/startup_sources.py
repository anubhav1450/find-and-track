"""Public startup boards discovered through employer postings; no login or cookies."""
import json
from urllib.request import Request,urlopen
from urllib.parse import urlsplit

ASHBY_BOARDS = {
    'sarvam':'Sarvam AI','composio':'Composio','outmarket':'Outmarket AI',
    'emergence':'Emergence Software','interview-kickstart':'Interview Kickstart',
}


def ashby_posts(board):
    request=Request('https://api.ashbyhq.com/posting-api/job-board/'+board+'?includeCompensation=true',headers={
        'Accept':'application/json','User-Agent':'FindAndTrack/0.4'})
    with urlopen(request,timeout=15) as response:raw=response.read(12_000_001)
    if len(raw)>12_000_000:raise ValueError('Job board exceeds response size limit.')
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get('jobs'),list):raise ValueError('Invalid Ashby job board response.')
    posts=[]
    for job in data['jobs']:
        if not isinstance(job,dict) or job.get('isListed') is not True:continue
        url=job.get('jobUrl','')
        if not isinstance(url,str):continue
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname!='jobs.ashbyhq.com' or not parts.path.startswith('/'+board+'/'):continue
        locations=[job.get('location','')]+[row.get('location','') for row in job.get('secondaryLocations',[]) if isinstance(row,dict)]
        posts.append({'id':parts.path.strip('/').split('/')[-1], 'text':job.get('title'),
                      'hostedUrl':url,'descriptionPlain':job.get('descriptionPlain') or '',
                      'categories':{'location':'; '.join(x for x in locations if isinstance(x,str)),
                                    'commitment':job.get('employmentType') or 'Unconfirmed'},
                      'workplaceType':job.get('workplaceType') or 'Unconfirmed',
                      'publishedAt':job.get('publishedAt'),
                      'dateMeaning':'Last published by employer; may be a repost'})
    return posts
