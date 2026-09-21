import http from 'k6/http'; import {check,sleep} from 'k6';
export const options={stages:[{duration:'10s',target:10},{duration:'20s',target:25},{duration:'10s',target:0}],thresholds:{http_req_failed:['rate<0.01'],http_req_duration:['p(95)<750']}};
const BASE=__ENV.BASE_URL||'http://localhost:8080';
export function setup(){const r=http.get(`${BASE}/api/auth/demo-token?role=operator&tenant_id=meridian&mfa=true`);return {token:r.json('access_token')}}
export default function(data){const h={headers:{Authorization:`Bearer ${data.token}`,'Content-Type':'application/json'}};check(http.get(`${BASE}/api/overview`,h),{'overview 200':r=>r.status===200});check(http.post(`${BASE}/api/tasks`,JSON.stringify({request:'Which products need reorder?'}),h),{'task accepted':r=>r.status===200});sleep(.25)}
