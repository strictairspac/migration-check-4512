import {readdir,readFile} from 'node:fs/promises';
// minimal DOM stubs
globalThis.document={getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[],hidden:false};
globalThis.window={scrollTo(){}};globalThis.sessionStorage={getItem:()=>null,setItem(){},removeItem(){}};
globalThis.fetch=async()=>({ok:true,json:async()=>({version:0,edges:[]})});
// rewrite relative imports by loading modules from a temp dir mirror is complex; instead dynamic import the real files
const mod=await import('/workspace/frontend/src/pages/lineage.js');
const store=(await import('/workspace/frontend/src/stores/business.js')).store;
store.user={email:'op@x',role:'operator'};
store.lineage={version:3,edges:[{sample_code:'M1',parent_sample_code:'A',relation:'mix',relation_label:'混样',version:1,created_by:'op',note:'demo'},{sample_code:'A',parent_sample_code:'P',relation:'split',relation_label:'分样',version:2,created_by:'op',note:''}]};
store.traceResult={code:'P',matched:2,runs:[{run_id:1,run_name:'run-1',batch_id:1,lineage_version:2,lineage_source:'registered',count:2,rows:[{ordinal:0,sample_code:'M1',test_name:'T1',result_value:'1.5',provenance_paths:[['M1','A','P']],roots:['P'],attribution:'registered'}]}]};
const html=mod.lineagesPage();
for(const needle of ['补登记父样来路','当前谱系','v3','分样','混样','追查受影响结果','M1','A','P'])if(!html.includes(needle))throw new Error('missing '+needle);
if(html.includes('undefined'))throw new Error('undefined leaked into page');
console.log('lineage page renders ok, length',html.length);
const res=await import('/workspace/frontend/src/pages/results.js');
const store2=(await import('/workspace/frontend/src/stores/business.js')).store;
store2.runs=[{id:1,name:'run',status:'completed',result:{source_count:2,accepted_count:2,rejected_count:0,rejected_rows:[],chunks:[{chunk:1,processed:2,accepted:2,rejected:0}],accepted_rows:[],checksum:'abc'},lineage:{version:2,source:'registered',captured_at:'now'}}];
const rh=res.resultsPage(1);
if(!rh.includes('谱系 v2'))throw new Error('results page missing lineage version');
if(!rh.includes('按落库时认定'))throw new Error('results page missing source label');
console.log('results page renders lineage ok');
