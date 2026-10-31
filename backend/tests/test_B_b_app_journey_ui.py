"""안내 공용 가짜 API. 동작 시험은 test_B_b_app_guide_ui.py로 옮겼다."""
import pytest

from test_B_b_app_dom import run_js


SETUP = r"""
const clone=x=>JSON.parse(JSON.stringify(x));
const el=id=>document.getElementById(id);
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
let saved=journeyDefault(), puts=[], gets=0, failRead=false, failWrite=false;
let runData={name:'fake-run',weighted:71,key:{id:'silver/fake',label:'Fake answers'},set:{id:'fake-set'},
 status_text:{top_problem:{name:'Fake criterion',section:8,loss:2,docs:[{doc_id:'T21-X01'}]}}};
const options={sets:[{id:'fake-set',usable:true,docs:[{doc_id:'T21-X01',runnable:{try:true}}]}],models:[{tag:'fake-model',connected:false}]};
api=async(path,opts={})=>{
 if(path==='/api/journey'){
  if(opts.method==='PUT'){const body=JSON.parse(opts.body);puts.push(clone(body));if(failWrite)throw new Error('write denied');saved=clone(body.journey);return {journey:clone(saved),problems:[]};}
  gets++;if(failRead)throw new Error('read denied');return {journey:clone(saved),problems:[]};
 }
 if(path.startsWith('/api/runs'))return {current:runData?.name,runs:runData?[runData]:[]};
 if(path.startsWith('/api/run/'))return clone(runData);
 if(path==='/api/options')return options;
 if(path==='/api/jobs')return {jobs:[],running:[]};
 if(path==='/api/servers')return {models:[]};
 if(path==='/api/sets')return {sets:options.sets,default:'fake-set'};
 if(path==='/api/keys')return {keys:[{id:'silver/fake',usable:true}],default:'silver/fake'};
 throw new Error(path);
};
post=async()=>{throw new Error('Unexpected POST');};
S.ctx={set:'fake-set',key:'silver/fake'};S.shell.contextLoaded=true;
S.shell.keys=[{id:'silver/fake',usable:true}];S.shell.servers={models:[]};
const target={run:'fake-run',doc:'T21-X01',section:8,item:'Fake criterion'};
const evidence={...target,mismatch:true,line:'p2:L3',path:'fake.value'};
"""
