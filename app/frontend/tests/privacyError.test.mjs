import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';

test('privacy block is shown in Turkish for structured API errors',async()=>{
 const server=await createServer({configFile:false,appType:'custom',server:{middlewareMode:true,hmr:false,ws:false,watch:null}});
 const originals={fetch:globalThis.fetch,window:globalThis.window,localStorage:globalThis.localStorage};
 globalThis.window={location:{hash:'#/case'}};
 globalThis.localStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{}};
 try{
  const {privacyErrorMessage,PRIVACY_FAILURE_MESSAGE}=await server.ssrLoadModule('/src/services/privacyError.ts');
  const body={code:'PRIVACY_REDACTION_FAILED',detail:'ignored transport text'};
  assert.equal(privacyErrorMessage(body),PRIVACY_FAILURE_MESSAGE);
  assert.equal(privacyErrorMessage({detail:{code:body.code}}),PRIVACY_FAILURE_MESSAGE);
  assert.equal(privacyErrorMessage({detail:'Normal hata'}),undefined);
  globalThis.fetch=async()=>new Response(JSON.stringify(body),{status:422,headers:{'Content-Type':'application/json'}});
  const {apiClient}=await server.ssrLoadModule('/src/services/apiClient.ts');
  await assert.rejects(apiClient.post('/test',{}),error=>error.message===PRIVACY_FAILURE_MESSAGE);
  const simple=await server.ssrLoadModule('/src/services/simpleCaseClient.ts');
  await assert.rejects(simple.normalizeSimpleCase({clinical:{},labs:[],reports:[]}),error=>error.message===PRIVACY_FAILURE_MESSAGE);
  let requested;
  globalThis.fetch=async(url)=>{requested=String(url);return new Response('[]',{status:200,headers:{'Content-Type':'application/json'}});};
  await simple.uploadLabPdf(new File(['synthetic'],'synthetic.pdf'),undefined,'00000000-0000-0000-0000-000000000001');
  assert.ok(requested.includes('patient_id=00000000-0000-0000-0000-000000000001'));
  await simple.uploadLabPdf(new File(['synthetic'],'synthetic.pdf'));
  assert.ok(!requested.includes('patient_id='));
 }finally{Object.assign(globalThis,originals);await server.close();}
});
