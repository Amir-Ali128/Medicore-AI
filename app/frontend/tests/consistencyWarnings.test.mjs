import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
test('consistency panel renders per-row Turkish provenance and empty state',async()=>{
  const server=await createServer({configFile:false,appType:'custom',server:{middlewareMode:true,hmr:false,ws:false,watch:null}});
  try{
    const Panel=(await server.ssrLoadModule('/src/components/clinical/ConsistencyWarnings.tsx')).default;
    const flag={code:'numeric_value_conflict',severity:'high',parameter_or_report:'Hb',date:'2026-10-01',source_page:2,source_row:4,message_tr:'Ham değer ile sayısal okuma uyuşmuyor.'};
    const html=renderToStaticMarkup(React.createElement(Panel,{flags:[flag,flag]}));
    for(const word of ['Hb','Sayfa 2','Satır 4','Yüksek öncelikli','Ham değer'])assert.ok(html.includes(word));
    assert.equal((html.match(/<li /g)||[]).length,1);
    assert.ok(renderToStaticMarkup(React.createElement(Panel,{flags:[]})).includes('Tespit edilen veri tutarsızlığı yok.'));
  }finally{await server.close();}
});
