/** @typedef {{id:number,name:string,source_file:string,rows:object[]}} Batch */
/** @typedef {{id:number,name:string,batch_id:number,rules:object[],chunk_size:number}} Mapping */
/** @typedef {{id:number,name:string,status:'queued'|'running'|'completed'|'failed'|'cancelled',result:object|null,lineage:object|null}} Run */
/** @typedef {{sample_code:string,parent_sample_code:string,relation:'split'|'mix'}} LineageEntry */
/** @typedef {{sample_code:string,parent_sample_code:string,relation:string,relation_label:string,version:number,note:string,created_by:string,created_at:string}} LineageEdge */
/** @typedef {{version:number,replayed:boolean,accepted:boolean,unchanged?:boolean,lines:object[]}} LineageRegistrationResult */
export {};
