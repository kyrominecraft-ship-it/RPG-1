import shutil
import subprocess
import unittest
from pathlib import Path


class ChatRenderingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is optional for the development-only renderer test')
    def test_safe_paragraph_heading_and_inline_formatting(self):
        module = str(Path(__file__).parents[1] / 'rpg/chat.js')
        script = r'''
const assert=require('node:assert/strict');
class Element {
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.value='';}
 append(...children){this.children.push(...children);}
 set textContent(value){this.children=[];this.value=value;}
 get textContent(){return this.value+this.children.map(c=>c.textContent).join('');}
}
global.document={createElement:tag=>new Element(tag),createTextNode:text=>({tagName:'#text',textContent:text})};
const chat=require(process.argv[1]);
const body=chat.narrative('### Scene\r\n\r\nFirst **bold** paragraph.\r\n\r\nSecond *quiet* paragraph.\r\n\r\n---\r\n\r\n1. An example\r\n2. Another\r\n\r\n<img src=x onerror=alert(1)>');
assert.deepEqual(body.children.map(c=>c.tagName),['H4','P','P','HR','OL','P']);
assert.equal(body.children[0].textContent,'Scene');
assert.equal(body.children[1].textContent,'First bold paragraph.');
assert.ok(body.children[1].children.some(c=>c.tagName==='STRONG'));
assert.equal(body.children[2].textContent,'Second quiet paragraph.');
assert.ok(body.children[2].children.some(c=>c.tagName==='EM'));
assert.equal(body.children[5].textContent,'<img src=x onerror=alert(1)>');
assert.equal(body.children[5].children[0].tagName,'#text');
const turn=chat.turn('My exact words.\nMy action.','One response.');
assert.equal(turn.children.length,2);
assert.equal(turn.children[0].children[1].textContent,'My exact words.\nMy action.');
assert.equal(turn.children[1].children[1].textContent,'One response.');
'''
        result = subprocess.run(['node', '-e', script, module], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
