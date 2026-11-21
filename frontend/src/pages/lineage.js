import {store} from '../stores/business.js';import {esc,json} from '../utils/html.js';import {table} from '../components/common/table.js';import {RELATIONS} from '../constants/enums.js';
const entryRow=()=>`<tr class="lineage-entry"><td><input name="sample_code" placeholder="子样 / 混样编号" required></td><td><input name="parent_sample_code" placeholder="父样编号" required></td><td><select name="relation">${Object.entries(RELATIONS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></td><td><button type="button" class="quiet" data-drop-entry>移除</button></td></tr>`;
export const newReceipt=()=>'lr-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10);
export function lineagesPage(){
 const edges=store.lineage.edges||[];const trace=store.traceResult;const receipt=store.lastReceipt?.request_id||newReceipt();
 return `<div class="split"><section><h2>补登记父样来路</h2><p>分样每条只有一个父样；混样的每一条来路都要登记。回执编号用于重试去重，同一次登记重发不会重复登记。</p><form id="lineage-form"><input type="hidden" name="request_id" value="${esc(receipt)}"><label>回执编号（自动生成，可手工填写）<input name="request_id_visible" value="${esc(receipt)}" required></label><label>备注<input name="note" placeholder="例如：11月18日分样复核"></label><table class="lineage-editor"><thead><tr><th>子样 / 混样</th><th>父样</th><th>关系</th><th></th></tr></thead><tbody id="lineage-entries">${entryRow()}</tbody></table><div class="actions"><button type="button" class="quiet" data-add-entry>＋ 增加一条来路</button><button type="submit">提交父样登记</button><button type="button" class="quiet" data-new-receipt>换一个回执编号</button></div><small>并发补录若两单合起来成环，后到的一单整单退回，另一单照常入库；无关支系不受影响。</small></form><h3>按原样追查已入库结果</h3><form id="trace-form"><label>原样 / 父样 / 混样编号<input name="code" placeholder="JS-20261117-001" required value="${esc(store.lastTraceCode||'')}"></label><button type="submit">追查受影响结果 →</button></form>${trace?traceBlock(trace):''}</section><section><h2>当前谱系 <em>v${store.lineage.version??0}</em></h2><p>读取的是当前认定的来路；每次迁移落库时冻结当时版本，之后补录不会改写已入库结果的来路认定。</p>${table(['子样 / 混样','父样','关系 / 版本'],edges.map(e=>[`<b>${esc(e.sample_code)}</b><small>${esc(e.note||'')}</small>`,`<span class="mono-inline">${esc(e.parent_sample_code)}</span>`,`<span class="status">${esc(e.relation_label||RELATIONS[e.relation]||e.relation)}</span><small>v${e.version} · ${esc(e.created_by)}</small>`]))}<aside class="note">旧备份恢复后仍按该运行落库时认定的谱系追查；当时未登记父样的行，按原样自身归档，不向上追溯。</aside></section></div>`;}
function traceBlock(trace){
 if(!trace.matched)return `<div class="empty">没有找到与 <b>${esc(trace.code)}</b> 相关的已入库结果。</div>`;
 return `<div class="metrics"><div><small>命中原样</small><strong>${esc(trace.code)}</strong></div><div><small>受影响结果</small><strong>${trace.matched}<em>行</em></strong></div><div><small>涉及运行</small><strong>${trace.runs.length}<em>次</em></strong></div></div><h3>受影响结果 · 按运行</h3>${trace.runs.map(run=>`<div class="trace-run"><div class="trace-head"><b>${esc(run.run_name)}</b><small>运行 #${run.run_id} · 谱系 v${run.lineage_version} · ${run.lineage_source==='legacy'?'旧数据按原样追查':'登记谱系'} · ${run.count} 行</small></div>${table(['序','原样','检测项','结果','来路路径'],run.rows.map(x=>[x.ordinal+1,esc(x.sample_code),esc(x.test_name),esc(x.result_value),x.provenance_paths.map(p=>esc(p.join(' ← '))).join('<br>')||'<small>原样自身</small>']))}</div>`).join('')}`;}
export function bindLineage(){
 const form=document.getElementById('lineage-form');
 if(!form)return;
 const sync=()=>{const visible=form.querySelector('[name=request_id_visible]');form.querySelector('[name=request_id]').value=visible.value.trim();};
 form.querySelector('[name=request_id_visible]').addEventListener('input',sync);
 form.addEventListener('click',e=>{
  if(e.target.matches('[data-add-entry]'))document.getElementById('lineage-entries').insertAdjacentHTML('beforeend',entryRow());
  if(e.target.matches('[data-drop-entry]')){const rows=form.querySelectorAll('.lineage-entry');if(rows.length>1)e.target.closest('tr').remove();}
  if(e.target.matches('[data-new-receipt]')){const id=newReceipt();form.querySelector('[name=request_id_visible]').value=id;sync();}
 });
}
export function readLineageForm(form){
 const entries=[...form.querySelectorAll('.lineage-entry')].map(tr=>{
  const fields=tr.querySelectorAll('input,select');const [sample,parent,relation]=fields;
  return {sample_code:sample.value.trim(),parent_sample_code:parent.value.trim(),relation:relation.value};
 }).filter(e=>e.sample_code||e.parent_sample_code);
 return {request_id:form.querySelector('[name=request_id_visible]').value.trim(),note:form.elements.note.value.trim(),entries};
}
