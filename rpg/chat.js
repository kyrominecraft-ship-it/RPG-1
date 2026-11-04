/* Small safe display formatter. No generated text is parsed as HTML. */
(function(root) {
 'use strict';
 function inline(parent, text) {
  const pattern=/\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g;
  let start=0, match;
  while((match=pattern.exec(text))) {
   parent.append(document.createTextNode(text.slice(start,match.index)));
   const node=document.createElement(match[1]!==undefined?'strong':'em');
   node.textContent=match[1]!==undefined?match[1]:match[2];parent.append(node);start=pattern.lastIndex;
  }
  parent.append(document.createTextNode(text.slice(start)));
 }
 function narrative(text) {
  const container=document.createElement('div');container.className='narrative';
  let paragraph=[], list=null;
  function flush(){if(paragraph.length){const p=document.createElement('p');inline(p,paragraph.join(' '));container.append(p);paragraph=[];}}
  for(const line of text.replace(/\r\n?/g,'\n').split('\n')) {
   if(!line.trim()){flush();list=null;continue;}
   const heading=line.match(/^\s*#{1,6}\s+(.+)$/), item=line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)$/);
   if(heading){flush();list=null;const h=document.createElement('h4');inline(h,heading[1]);container.append(h);}
   else if(/^\s*(?:---+|\*\*\*+)\s*$/.test(line)){flush();list=null;container.append(document.createElement('hr'));}
   else if(item){flush();const tag=item[1]?'ul':'ol';if(!list||list.tagName.toLowerCase()!==tag){list=document.createElement(tag);container.append(list);}const li=document.createElement('li');inline(li,item[2]);list.append(li);}
   else {list=null;paragraph.push(line.trim());}
  }
  flush();return container;
 }
 function turn(action, response) {
  const article=document.createElement('article');article.className='chat-turn';
  const player=document.createElement('section');player.className='player-message';
  const playerLabel=document.createElement('h3');playerLabel.textContent='You';
  const input=document.createElement('p');input.className='player-input';input.textContent=action;
  player.append(playerLabel,input);
  const gm=document.createElement('section');gm.className='gm-message';
  const gmLabel=document.createElement('h3');gmLabel.textContent='GM';gm.append(gmLabel,narrative(response));
  article.append(player,gm);return article;
 }
 const api={narrative,turn};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RPGChat=api;
})(typeof window!=='undefined'?window:globalThis);
