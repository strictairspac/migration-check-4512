import {batches,mappings,runs,lineage} from '../api/business.js';
export const store={batches:[],mappings:[],runs:[],lineage:{version:0,edges:[]},lastReceipt:null,lastTraceCode:'',traceResult:null,user:null};
export async function refresh(){[store.batches,store.mappings,store.runs,store.lineage]=await Promise.all([batches.list(),mappings.list(),runs.list(),lineage.list()]);}
