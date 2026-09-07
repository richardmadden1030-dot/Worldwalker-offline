"""Mobile NPC chat navigation regressions."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MobileChatTests(unittest.TestCase):
    def test_more_menu_includes_npc_chat(self):
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        more = html.split('id="modal-mobile-more"', 1)[1].split('data-mobile-open="advisor"', 1)[0]
        self.assertIn('data-mobile-open="chat"', more)
        self.assertIn('<b>NPC Chat</b>', more)

    @unittest.skipUnless(shutil.which("node"), "Node required for frontend behavior test")
    def test_shared_opener_refreshes_before_open_and_handles_errors(self):
        js = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
        opener = re.search(r'async function openNpcChat\(\) \{.*?\n\}', js, re.S).group()
        self.assertIn('$("#btn-open-chat").addEventListener("click", openNpcChat)', js)
        self.assertIn('if (target === "chat") openNpcChat();', js)
        program = """
const assert = require('node:assert/strict');
let calls = [], fail = false;
async function refreshChat() { calls.push('refresh'); if (fail) throw new Error('offline'); }
function openModal(id) { calls.push(id); }
function showToast(message, type) { calls.push([message, type]); }
""" + opener + """
(async () => {
  await openNpcChat();
  assert.deepEqual(calls, ['refresh', 'modal-chat']);
  calls = []; fail = true;
  await openNpcChat();
  assert.deepEqual(calls, ['refresh', ['offline', 'danger']]);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
