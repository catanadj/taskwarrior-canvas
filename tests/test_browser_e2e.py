import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from kyanbasu.runtime_html import build_runtime_html


class TestBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chromium = shutil.which("chromium")
        if not cls.chromium:
            raise unittest.SkipTest("Chromium not found; skipping browser E2E.")

        # Validate chromium is runnable in this environment.
        try:
            p = subprocess.run(
                [cls.chromium, "--headless", "--no-sandbox", "--dump-dom", "about:blank"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            raise unittest.SkipTest(f"Chromium probe failed in this environment ({type(e).__name__}).")
        if p.returncode != 0:
            raise unittest.SkipTest(
                f"Chromium unavailable in this environment (rc={p.returncode}); skipping browser E2E."
            )

    def _run_html_harness(self, html):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Kyanbasu.e2e.html"
            p.write_text(html, encoding="utf-8")
            try:
                out = subprocess.run(
                    [
                        self.chromium,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--virtual-time-budget=7000",
                        "--dump-dom",
                        f"file://{p}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                self.skipTest(f"Chromium execution failed in this environment ({type(e).__name__}).")
            if out.returncode != 0:
                self.skipTest(f"Chromium failed in this environment (rc={out.returncode}).")
            m = re.search(r'<pre id="e2e-out">(.*?)</pre>', out.stdout, flags=re.S)
            self.assertIsNotNone(m, "Harness output element not found in dumped DOM.")
            return m.group(1)

    def test_build_commands_shell_quotes_new_task_description_and_modifiers(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_COMMAND_HARNESS">
window.addEventListener('load', function(){
  try{
    window.TASKS.push({
      uuid:'new-e2e',
      short:'n-e2e',
      desc:"hello; world $(id) O'Reilly",
      project:'Work',
      tags:['safe'],
      has_depends:false
    });
    if (typeof updateConsole==='function') updateConsole();
    var out = (typeof buildCommands==='function') ? String(buildCommands()||'') : '';
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = out;
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")

        cmds = self._run_html_harness(html)
        self.assertNotIn("ERR:", cmds)
        self.assertIn("task add", cmds)
        self.assertIn("'project:Work' '+safe'", cmds)
        self.assertIn("'hello; world $(id) O'\"'\"'Reilly'", cmds)

    def test_kyanbasu_commands_core_normalizes_command_matrix(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_COMMAND_CORE_HARNESS">
window.addEventListener('load', function(){
  try{
    var raw = [
      "task abc modify +home",
      "task abc modify +home due:tomorrow",
      "task abc done",
      "task abc modify project:Later",
      "task def delete",
      "task def done",
      "task add Review O'Reilly $(id) project:Work +safe"
    ].join("\\n");
    var res = window.KyanbasuCommands.normalize(raw);
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = JSON.stringify({text:res.text, warnings:res.warnings});
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw_out = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw_out)
        result = json.loads(raw_out)
        text = result["text"]
        warnings = result["warnings"]

        self.assertIn("task 'abc' done", text)
        self.assertIn("task 'def' done", text)
        self.assertIn("task add 'Review O'\"'\"'Reilly $(id)' 'project:Work' '+safe'", text)
        self.assertNotIn("project:Later", text)
        self.assertTrue(any("Dropped modify after terminal action for task abc" in w for w in warnings))
        self.assertTrue(any("Conflicting terminal actions for task def" in w for w in warnings))

    def test_runtime_diagnostics_reports_perf_hot_paths(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_PERF_DIAG_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      if (typeof window.KyanbasuPerfReset === 'function') window.KyanbasuPerfReset();
      if (typeof updateConsole === 'function') updateConsole();
      if (typeof drawLinks === 'function') drawLinks();
      requestAnimationFrame(function(){});
      setTimeout(function(){}, 0);
      var marker = document.createElement('div');
      marker.id = 'perfMutationProbe';
      document.body.appendChild(marker);
      setTimeout(function(){
        var snap = window.KyanbasuPerfReport();
        var out = {
          hasDiagnostics: typeof window.KyanbasuDiagnostics === 'function',
          hasPerfReport: typeof window.KyanbasuPerfReport === 'function',
          functions: snap.perfSummary.topFunctions.map(function(x){ return x.name; }),
          timerCalls: snap.perfSummary.topTimers.reduce(function(n, x){ return n + x.calls; }, 0),
          hasRafMetrics: !!snap.perfSummary.raf && typeof snap.perfSummary.raf.fired === 'number',
          rafFired: snap.perfSummary.raf.fired,
          observersCreated: snap.perfSummary.observers.created,
          observerCallbacks: snap.perfSummary.observers.callbacks
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["hasDiagnostics"], msg=json.dumps(result))
        self.assertTrue(result["hasPerfReport"], msg=json.dumps(result))
        self.assertIn("updateConsole", result["functions"], msg=json.dumps(result))
        self.assertIn("drawLinks", result["functions"], msg=json.dumps(result))
        self.assertGreaterEqual(result["timerCalls"], 1, msg=json.dumps(result))
        self.assertTrue(result["hasRafMetrics"], msg=json.dumps(result))
        self.assertGreaterEqual(result["observersCreated"], 1, msg=json.dumps(result))

    def test_console_utility_runtimes_wire_toast_normalize_and_copy(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CONSOLE_UTILITIES_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      try{
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: { writeText: function(txt){ window.__copiedText = txt; return Promise.resolve(); } }
        });
      }catch(_){}
      var ct = document.getElementById('consoleText');
      ct.value = "task one\\ntask one\\\\ntask two";
      ct.dispatchEvent(new Event('input'));
      window.showToast("Ready");
      document.getElementById('copyBtn').click();
      setTimeout(function(){
        var out = {
          toast: (document.getElementById('devConsoleToast') || {}).textContent || "",
          console: ct.value,
          copied: window.__copiedText || "",
          flags: [
            !!window.__FEATURE_TOAST_UTIL_V1__,
            !!window.__FEATURE_CONSOLE_LINE_ENFORCER_V3__,
            !!window.__FEATURE_COPY_FULL_OVERRIDE_V1__,
            !!window.__FEATURE_SINGLE_CONSOLE_AUGMENT_V1__
          ]
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 0);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 600);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["flags"], [True, True, True, True])
        self.assertIn(result["toast"], ["Ready", "Copied 2 line(s)."])
        self.assertEqual(result["console"], "task one\ntask two")
        self.assertEqual(result["copied"], "task one\ntask two")

    def test_focus_and_project_add_tag_runtimes_dedupe_and_add_multiple_tags(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": ["old"],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
                "init_projects": ["Work"],
            }
        )
        html = build_runtime_html(base_html, payload, 1, lambda *_: None)

        harness = """
<script id="E2E_FOCUS_ADD_TAG_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.prompt = function(){ return "newtag extra old"; };
      var before = document.querySelectorAll('#builderStage .node[data-short="aaaaaaaa"]').length;
      if (typeof addToBuilder === 'function') addToBuilder(window.TASKS[0], 180, 180);
      var after = document.querySelectorAll('#builderStage .node[data-short="aaaaaaaa"]').length;
      var btn = document.querySelector('.projAreaLabel .projAddTagBtn');
      if (btn) btn.click();
      setTimeout(function(){
        var tags = Array.prototype.slice.call(document.querySelectorAll('.tagAreaLabel')).map(function(el){
          return (el.textContent || '').replace(/[+＋]\\s*$/, '').trim();
        }).sort();
        var out = {
          before: before,
          after: after,
          hasButton: !!btn,
          tags: tags,
          toast: (document.getElementById('devConsoleToast') || {}).textContent || "",
          flags: [
            !!window.__FEATURE_DEDUPE_FOCUS_V1__,
            !!window.__FEATURE_PROJECT_ADD_TAG_V4__
          ]
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["flags"], [True, True])
        self.assertTrue(result["hasButton"])
        self.assertEqual(result["before"], 1)
        self.assertEqual(result["after"], 1)
        self.assertIn("newtag", result["tags"])
        self.assertIn("extra", result["tags"])
        self.assertIn("old", result["tags"])
        self.assertIn('Added tags "newtag", "extra" to Work.', result["toast"])
        self.assertIn("Skipped: old (already exists)", result["toast"])

    def test_review_changes_runtime_groups_staged_command_core_output(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": ["old"],
                        "has_depends": False,
                    },
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Beta",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
                "init_projects": ["Work"],
            }
        )
        html = build_runtime_html(base_html, payload, 2, lambda *_: None)

        harness = """
<script id="E2E_REVIEW_CHANGES_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      try{
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: { writeText: function(txt){ window.__reviewCopiedText = txt; return Promise.resolve(); } }
        });
      }catch(_){}
      window.__reviewDownloads = [];
      window.__reviewObjectUrls = {};
      try{
        window.URL.createObjectURL = function(blob){
          var url = 'blob:review-' + Object.keys(window.__reviewObjectUrls).length;
          window.__reviewObjectUrls[url] = blob;
          return url;
        };
        window.URL.revokeObjectURL = function(url){ window.__reviewRevokedUrl = url; };
        HTMLAnchorElement.prototype.click = function(){
          window.__reviewDownloads.push({href:this.href, download:this.download});
        };
      }catch(_){}
      window.TASKS.push({
        uuid:"new-review",
        short:"new-rev",
        desc:"Review panel task",
        project:"Inbox",
        tags:["fresh"],
        has_depends:false
      });
      window.EX_OPS = window.__EXISTING_OPS__ = {
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {done:false, deleted:false, mods:["due:tomorrow"]},
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": {done:true, deleted:false, mods:[]}
      };
      window.stagedAdd = [{from:"aaaaaaaa", to:"bbbbbbbb"}];
      if (typeof updateConsole === 'function') updateConsole();
      document.getElementById('reviewChangesBtn').click();
      setTimeout(function(){
        var current = window.KyanbasuReview.current();
        var panel = document.getElementById('reviewChangesPanel');
        var copyBtn = document.getElementById('reviewCopyBtn');
        var downloadBtn = document.getElementById('reviewDownloadBtn');
        if (copyBtn) copyBtn.click();
        if (downloadBtn) downloadBtn.click();
        setTimeout(function(){
        var download = (window.__reviewDownloads || [])[0] || {};
        var blob = window.__reviewObjectUrls ? window.__reviewObjectUrls[download.href] : null;
        var scriptPromise = blob && blob.text ? blob.text() : Promise.resolve("");
        scriptPromise.then(function(scriptText){
        var out = {
          open: panel && panel.classList.contains('open'),
          button: !!document.getElementById('reviewChangesBtn'),
          copyButton: !!copyBtn,
          copyDisabled: copyBtn ? copyBtn.disabled : null,
          downloadButton: !!downloadBtn,
          downloadDisabled: downloadBtn ? downloadBtn.disabled : null,
          downloadName: download.download || "",
          downloadHref: download.href || "",
          scriptText: scriptText,
          copied: window.__reviewCopiedText || "",
          groups: {
            newTasks: current.groups.newTasks.length,
            terminal: current.groups.terminal.length,
            completions: current.groups.completions.length,
            deletions: current.groups.deletions.length,
            fieldChanges: current.groups.fieldChanges.length,
            dependencies: current.groups.dependencies.length,
            dependencyAdds: current.groups.dependencyAdds.length,
            dependencyRemoves: current.groups.dependencyRemoves.length,
            other: current.groups.other.length
          },
          text: panel ? panel.textContent : "",
          raw: current.text,
          preflight: current.preflight,
          impact: current.impact
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
        });
        }, 80);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["button"])
        self.assertTrue(result["open"])
        self.assertTrue(result["copyButton"])
        self.assertFalse(result["copyDisabled"])
        self.assertTrue(result["downloadButton"])
        self.assertFalse(result["downloadDisabled"])
        self.assertEqual(result["downloadName"], "kyanbasu-reviewed-commands.sh")
        self.assertTrue(result["downloadHref"].startswith("blob:review-"), msg=json.dumps(result))
        self.assertEqual(result["copied"], result["raw"])
        self.assertTrue(result["scriptText"].startswith("#!/usr/bin/env bash\nset -euo pipefail"), msg=json.dumps(result))
        self.assertIn(result["raw"], result["scriptText"])
        self.assertEqual(result["groups"]["newTasks"], 1)
        self.assertEqual(result["groups"]["terminal"], 1)
        self.assertEqual(result["groups"]["completions"], 1)
        self.assertEqual(result["groups"]["deletions"], 0)
        self.assertGreaterEqual(result["groups"]["fieldChanges"], 1)
        self.assertEqual(result["groups"]["dependencies"], 1)
        self.assertEqual(result["groups"]["dependencyAdds"], 1)
        self.assertEqual(result["groups"]["dependencyRemoves"], 0)
        self.assertTrue(result["preflight"]["ok"])
        self.assertEqual(result["preflight"]["errors"], 0)
        self.assertEqual(result["impact"]["counts"]["newTasks"], 1)
        self.assertEqual(result["impact"]["counts"]["completions"], 1)
        self.assertEqual(result["impact"]["counts"]["deletions"], 0)
        self.assertEqual(result["impact"]["counts"]["dependencyAdds"], 1)
        self.assertEqual(result["impact"]["counts"]["dependencyRemoves"], 0)
        self.assertGreaterEqual(result["impact"]["counts"]["fieldChanges"], 1)
        self.assertGreaterEqual(len(result["impact"]["rows"]), 4)
        self.assertGreaterEqual(len(result["impact"]["destructive"]), 1)
        self.assertIn("Review Changes", result["text"])
        self.assertIn("Impact Summary", result["text"])
        self.assertIn("Creates task: Review panel task", result["text"])
        self.assertIn("aaaaaaaa · Alpha: due date changes to tomorrow", result["text"])
        self.assertIn("aaaaaaaa · Alpha: will depend on bbbbbbbb · Beta", result["text"])
        self.assertIn("bbbbbbbb · Beta will be marked done", result["text"])
        self.assertIn("Needs attention", result["text"])
        self.assertIn("New Tasks", result["text"])
        self.assertIn("Completed Tasks", result["text"])
        self.assertIn("Dependency Adds", result["text"])
        self.assertIn("aaaaaaaa · Alpha", result["text"])
        self.assertIn("task add 'Review panel task'", result["raw"])

    def test_review_changes_preflight_blocks_invalid_staged_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
                "init_projects": ["Work"],
            }
        )
        html = build_runtime_html(base_html, payload, 1, lambda *_: None)

        harness = """
<script id="E2E_REVIEW_PREFLIGHT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      try{
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: { writeText: function(txt){ window.__reviewCopiedText = txt; return Promise.resolve(); } }
        });
      }catch(_){}
      window.__reviewDownloads = [];
      try{
        HTMLAnchorElement.prototype.click = function(){
          window.__reviewDownloads.push({href:this.href, download:this.download});
        };
      }catch(_){}
      window.STAGED_CMDS = [
        "task aaaaaaaa modify depends:aaaaaaaa",
        "task aaaaaaaa modify",
        "rm -rf nope"
      ];
      if (typeof updateConsole === 'function') updateConsole();
      document.getElementById('reviewChangesBtn').click();
      setTimeout(function(){
        var current = window.KyanbasuReview.current();
        var panel = document.getElementById('reviewChangesPanel');
        var copyBtn = document.getElementById('reviewCopyBtn');
        var downloadBtn = document.getElementById('reviewDownloadBtn');
        if (copyBtn) copyBtn.click();
        if (downloadBtn) downloadBtn.click();
        setTimeout(function(){
        var out = {
          preflight: current.preflight,
          copyButton: !!copyBtn,
          copyDisabled: copyBtn ? copyBtn.disabled : null,
          downloadButton: !!downloadBtn,
          downloadDisabled: downloadBtn ? downloadBtn.disabled : null,
          downloads: (window.__reviewDownloads || []).length,
          copied: window.__reviewCopiedText || "",
          text: panel ? panel.textContent : ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
        }, 80);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertFalse(result["preflight"]["ok"], msg=json.dumps(result))
        self.assertEqual(result["preflight"]["errors"], 2, msg=json.dumps(result))
        self.assertEqual(result["preflight"]["warnings"], 1, msg=json.dumps(result))
        self.assertTrue(result["copyButton"], msg=json.dumps(result))
        self.assertTrue(result["copyDisabled"], msg=json.dumps(result))
        self.assertTrue(result["downloadButton"], msg=json.dumps(result))
        self.assertTrue(result["downloadDisabled"], msg=json.dumps(result))
        self.assertEqual(result["downloads"], 0, msg=json.dumps(result))
        self.assertEqual(result["copied"], "", msg=json.dumps(result))
        self.assertIn("Preflight blocked", result["text"])
        self.assertIn("Only task commands are supported", result["text"])
        self.assertIn("A task cannot depend on itself", result["text"])
        self.assertIn("Empty modify command", result["text"])

    def test_done_delete_toggle_does_not_duplicate_console_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
                "init_projects": ["Work"],
            }
        )
        html = build_runtime_html(base_html, payload, 1, lambda *_: None)

        harness = """
<script id="E2E_DONE_DELETE_DUP_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var btn = document.querySelector('#builderStage .node[data-short="aaaaaaaa"] .btnDone');
      if (!btn) throw new Error('done button missing');
      btn.click();
      var immediate = (document.getElementById('consoleText') || {}).value || "";
      setTimeout(function(){
        var early = (document.getElementById('consoleText') || {}).value || "";
        setTimeout(function(){
          var text = (document.getElementById('consoleText') || {}).value || "";
          var raw = (window.STAGED_CMDS || []).slice();
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify({immediate:immediate, early:early, text:text, staged:raw});
          document.body.appendChild(pre);
        }, 260);
      }, 80);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["staged"], [])
        immediate_lines = [line for line in result["immediate"].splitlines() if line.strip()]
        early_lines = [line for line in result["early"].splitlines() if line.strip()]
        final_lines = [line for line in result["text"].splitlines() if line.strip()]
        self.assertLessEqual(len(immediate_lines), 1)
        self.assertEqual(len(early_lines), 1)
        self.assertEqual(len(final_lines), 1)
        self.assertRegex(final_lines[0], r"^task '?[0-9a-f-]+'? done$")

    def test_task_hover_buttons_do_not_start_card_drag_and_can_be_clicked(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Bravo",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
                "init_projects": ["Work"],
            }
        )
        html = build_runtime_html(base_html, payload, 1, lambda *_: None)

        harness = """
<script id="E2E_HOVER_BUTTON_DRAG_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var node = document.querySelector('#builderStage .node[data-short="bbbbbbbb"]');
      if (!node) throw new Error('task node missing');
      var btn = node.querySelector('.btnDone');
      if (!btn) throw new Error('done button missing');
      var before = {left: node.style.left, top: node.style.top};
      btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, clientX:10, clientY:10}));
      document.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, cancelable:true, clientX:260, clientY:220}));
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, clientX:260, clientY:220}));
      var afterDrag = {left: node.style.left, top: node.style.top};
      btn.click();
      setTimeout(function(){
        var text = (document.getElementById('consoleText') || {}).value || "";
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify({
          before: before,
          afterDrag: afterDrag,
          stagedDone: node.classList.contains('stagedDone'),
          text: text
        });
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["afterDrag"], result["before"])
        self.assertTrue(result["stagedDone"])
        self.assertRegex(result["text"], r"task '?[0-9a-f-]+'? done")

    def test_canvas_storage_key_is_stable_and_snapshots_are_bounded_and_restorable(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "workspace_id": "storage-contract",
                "tasks": [],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_STORAGE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var storage = window.KyanbasuStorage;
      var keyBefore = storage.key('probe');
      for (var i=1; i<=8; i++) storage.setJSON('probe', {value:i}, {snapshot:true});
      var historyBeforeRestore = storage.snapshots('probe').map(function(row){
        return JSON.parse(row.raw).value;
      });
      var restored = storage.restoreSnapshot('probe', 4);
      window.DATA.tasks.push({uuid:'changed-task-set'});
      var out = {
        keyBefore:keyBefore,
        keyAfter:storage.key('probe'),
        workspaceId:storage.workspaceId(),
        history:historyBeforeRestore,
        restored:restored && restored.value,
        current:storage.getJSON('probe', null).value
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["workspaceId"], "storage-contract")
        self.assertEqual(result["keyAfter"], result["keyBefore"])
        self.assertEqual(result["history"], [7, 6, 5, 4, 3])
        self.assertEqual(result["restored"], 3)
        self.assertEqual(result["current"], 3)

    def test_kyanbasu_storage_uses_canonical_workspace_and_snapshots(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "workspace_id": "storage-canonical",
                "tasks": [],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)
        prelude = """
<script id="E2E_KYANBASU_STORAGE_PRELUDE">
localStorage.setItem('kyanbasu:workspace:v1:storage-canonical:probe', JSON.stringify({value:41}));
localStorage.setItem('kyanbasu:workspace:v1:storage-canonical:probe:snapshots', JSON.stringify([{savedAt:1, raw:'{"value":40}'}]));
</script>
"""
        html = html.replace("<body>", "<body>" + prelude, 1)
        harness = """
<script id="E2E_KYANBASU_STORAGE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var storage = window.KyanbasuStorage;
      var key = storage.key('probe');
      var value = storage.getJSON('probe', null);
      var history = storage.snapshots('probe');
      storage.setJSON('new-only', {value:42});
      var out = {
        key:key,
        value:value && value.value,
        historyValue:history[0] && JSON.parse(history[0].raw).value,
        newOnly:storage.getJSON('new-only', null).value
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["key"].startswith("kyanbasu:workspace:v1:"), msg=json.dumps(result))
        self.assertEqual(result["value"], 41, msg=json.dumps(result))
        self.assertEqual(result["historyValue"], 40, msg=json.dumps(result))
        self.assertEqual(result["newOnly"], 42)

    def test_kyanbasu_browser_apis_are_available(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)
        harness = """
<script id="E2E_KYANBASU_API_ALIAS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var suffixes = ['Commands','ConsoleEditor','ContextBar','DependencyEdges','Diagnostics','EdgeDirection','LayoutPersist','Navigator','Notes','NotesCore','PerfReport','PerfReset','QuickAdd','Review','Storage','Workbenches'];
      var missing = suffixes.filter(function(suffix){
        return !window['Kyanbasu' + suffix] || window['Kyanbasu' + suffix] !== window['Kyanbasu' + suffix];
      });
      var out = {
        missing:missing
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["missing"], [], msg=json.dumps(result))

    def test_canvas_notes_runtime_creates_links_and_stays_out_of_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 220, "Plan", "Break work down");
      var b = window.KyanbasuNotes.createNote(560, 250, "Step 1", "Trace current flow");
      window.KyanbasuNotes.linkNotes(a.id, b.id);
      window.KyanbasuNotes.save();
      window.KyanbasuNotes.setContent(b.id, 'Updated step');
      window.KyanbasuNotes.save();
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var out = {
          noteButton: !!document.getElementById('noteModeBtn'),
          linkButton: !!document.getElementById('noteLinkModeBtn'),
          notes: document.querySelectorAll('.tcNoteNode').length,
          textFields: document.querySelectorAll('.tcNoteNode .tcNoteText').length,
          titleFields: document.querySelectorAll('.tcNoteNode .tcNoteTitle').length,
          links: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink').length,
          directionSources: document.querySelectorAll('#tcNoteLinksLayer .tcNoteDirectionSource').length,
          directionArrows: document.querySelectorAll('#tcNoteLinksLayer .tcNoteDirectionArrow').length,
          directionChevrons: document.querySelectorAll('#tcNoteLinksLayer .tcNoteDirectionChevron').length,
          apiNotes: window.KyanbasuNotes.notes().length,
          apiLinks: window.KyanbasuNotes.links().length,
          coreVersion: window.KyanbasuNotesCore && window.KyanbasuNotesCore.version,
          rejectsSelfChild: !window.KyanbasuNotesCore.validateLink(
            {from:a.id, to:a.id, type:'child'},
            [],
            {notes:window.KyanbasuNotes.notes()}
          ).ok,
          legacyContent: window.KyanbasuNotesCore.normalizeNote(
            {id:'legacy', title:'Old title', body:'Old body'},
            {}
          ).content,
          legacyKind: window.KyanbasuNotesCore.normalizeNote({id:'legacy-kind', content:'Legacy'}, {}).kind,
          legacyStatus: window.KyanbasuNotesCore.normalizeNote({id:'legacy-status', content:'Legacy'}, {}).status,
          unknownRelation: window.KyanbasuNotesCore.normalizeRelation('not-a-relation'),
          firstContent: window.KyanbasuNotes.notes()[0] && window.KyanbasuNotes.notes()[0].content,
          hasTitleKey: window.KyanbasuNotes.notes().some(function(n){ return Object.prototype.hasOwnProperty.call(n, 'title'); }),
          console: (document.getElementById('consoleText') || {}).value || "",
          savedKeys: Object.keys(localStorage).filter(function(k){ return k.indexOf('kyanbasu:workspace:v1:') === 0; }).length,
          storageKey: window.KyanbasuStorage.key('notes'),
          snapshotCount: window.KyanbasuStorage.snapshots('notes').length
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 80);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["noteButton"])
        self.assertTrue(result["linkButton"])
        self.assertEqual(result["notes"], 2)
        self.assertEqual(result["textFields"], 2)
        self.assertEqual(result["titleFields"], 0)
        self.assertEqual(result["links"], 1)
        self.assertEqual(result["directionSources"], 1)
        self.assertEqual(result["directionArrows"], 1)
        self.assertEqual(result["directionChevrons"], 1)
        self.assertEqual(result["apiNotes"], 2)
        self.assertEqual(result["apiLinks"], 1)
        self.assertEqual(result["coreVersion"], 7)
        self.assertTrue(result["rejectsSelfChild"])
        self.assertEqual(result["legacyContent"], "Old title\nOld body")
        self.assertEqual(result["legacyKind"], "note")
        self.assertEqual(result["legacyStatus"], "open")
        self.assertEqual(result["unknownRelation"], "manual")
        self.assertEqual(result["firstContent"], "Plan\nBreak work down")
        self.assertFalse(result["hasTitleKey"])
        self.assertEqual(result["console"], "")
        self.assertGreaterEqual(result["savedKeys"], 1)
        self.assertTrue(result["storageKey"].startswith("kyanbasu:workspace:v1:"))
        self.assertGreaterEqual(result["snapshotCount"], 1)

    def test_canvas_notes_roles_and_statuses_render_edit_search_and_export(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTE_SEMANTICS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var note = window.KyanbasuNotes.createNote(260, 220, 'What is blocking delivery?', '', 'Planning');
      window.KyanbasuNotes.setNoteKind(note.id, 'question');
      window.KyanbasuNotes.setNoteStatus(note.id, 'resolved');
      window.KyanbasuNotes.selectNote(note.id);
      setTimeout(function(){
        var kindSelect = document.getElementById('inspectorNoteKind');
        var statusSelect = document.getElementById('inspectorNoteStatus');
        var before = {
          kind:kindSelect && kindSelect.value,
          status:statusSelect && statusSelect.value,
          questionSearch:window.KyanbasuNotes.searchNotes('question'),
          resolvedSearch:window.KyanbasuNotes.searchNotes('resolved')
        };
        kindSelect.value = 'decision';
        kindSelect.dispatchEvent(new Event('change', {bubbles:true}));
        window.KyanbasuNotes.setNoteStatus(note.id, 'parked');
        setTimeout(function(){
          var card = document.querySelector('.tcNoteNode[data-note-id="'+note.id+'"]');
          var exported = window.KyanbasuNotes.exportData();
          document.getElementById('tabViewer').click();
          setTimeout(function(){
            var viewerSemantics = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerNoteSemantic')).map(function(el){ return el.textContent; });
            var out = {
              before:before,
              kind:window.KyanbasuNotes.notes()[0].kind,
              status:window.KyanbasuNotes.notes()[0].status,
              cardKind:(card.querySelector('.tcNoteKindBadge') || {}).textContent || '',
              cardStatus:(card.querySelector('.tcNoteStatusBadge') || {}).title || '',
              exportedVersion:exported.version,
              exportedKind:exported.notes[0].kind,
              exportedStatus:exported.notes[0].status,
              viewerSemantics:viewerSemantics
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 120);
        }, 120);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["before"]["kind"], "question")
        self.assertEqual(result["before"]["status"], "resolved")
        self.assertEqual(len(result["before"]["questionSearch"]), 1)
        self.assertEqual(len(result["before"]["resolvedSearch"]), 1)
        self.assertEqual(result["kind"], "decision")
        self.assertEqual(result["status"], "parked")
        self.assertEqual(result["cardKind"], "Decision")
        self.assertEqual(result["cardStatus"], "Status: Parked")
        self.assertEqual(result["exportedVersion"], 7)
        self.assertEqual(result["exportedKind"], "decision")
        self.assertEqual(result["exportedStatus"], "parked")
        self.assertEqual(result["viewerSemantics"], ["Decision", "Parked"])

    def test_canvas_decision_maps_commit_immutable_history_and_round_trip(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_DECISION_MAP_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var api = window.KyanbasuNotes;
      var created = api.createDecisionMap(180, 300, 'Decisions');
      var root = created.root;
      var optionA = created.options[0];
      var optionB = created.options[1];
      api.setContent(root.id, 'Decision: Choose a focus\\nTarget outcome: Ship a useful result\\nSuccess means: Used for one week\\nDecision needed by: Friday\\nReassess by: Next Friday');
      api.setContent(optionA.id, 'Option: Build the smaller workflow');
      api.setContent(optionB.id, 'Option: Keep the current process');
      var outcomeA = api.createChildNote(optionA.id);
      var outcomeB = api.createChildNote(optionB.id);
      api.setContent(outcomeA.id, 'Possible outcome: Faster planning\\nBest estimate: 60%\\nReasonable range: 40-75%\\nPayoff / cost: Less friction');
      api.setContent(outcomeB.id, 'Possible outcome: No migration cost\\nBest estimate: 80%\\nReasonable range: 65-90%\\nPayoff / cost: No improvement');
      var evidence = api.createChildNote(created.factor.id, 'Outside view: similar small workflows were adopted', '');
      api.setNoteKind(evidence.id, 'evidence');
      api.selectNote(optionA.id);
      setTimeout(function(){
        var checklist = api.decisionContext(optionA.id).checklist;
        var commitButton = document.getElementById('inspectorDecisionCommit');
        var inspectorChecklistPresent = !!document.getElementById('inspectorDecisionChecklist');
        var rationale = document.getElementById('inspectorDecisionRationale');
        if (rationale) rationale.value = 'Best fit for the current constraints';
        if (!commitButton) throw new Error('Decision commit control missing');
        commitButton.click();
        setTimeout(function(){
          var firstHistory = api.decisionHistory(root.id);
          api.setContent(optionA.id, 'Option: Edited after the first commitment');
          api.commitDecision(root.id, optionB.id, 'Lower immediate cost after new information');
          var history = api.decisionHistory(root.id);
          var firstOptionSnapshot = history.commits[0].notes.filter(function(note){ return note.id === optionA.id; })[0];
          var secondOptionSnapshot = history.commits[1].notes.filter(function(note){ return note.id === optionA.id; })[0];
          var exported = api.exportData();
          window.KyanbasuWorkbenches.capture();
          var workbenches = window.KyanbasuWorkbenches.exportData();
          var workbenchRoot = workbenches.workbenches[0].notes.notes.filter(function(note){ return note.id === root.id; })[0];
          api.importData(exported);
          setTimeout(function(){
            var importedHistory = api.decisionHistory(root.id);
            var chosenCard = document.querySelector('.tcNoteNode[data-note-id="'+optionB.id+'"]');
            var rootNote = api.notes().filter(function(note){ return note.id === root.id; })[0];
            var alternatives = api.notes().filter(function(note){ return note.id === optionA.id || note.id === optionB.id; });
            var kinds = api.noteKinds().map(function(item){ return item.value; });
            var out = {
              decisionButton:!!document.getElementById('noteDecisionBtn'),
              mapKinds:api.notes().map(function(note){ return note.kind; }),
              semanticKinds:[kinds.indexOf('factor') >= 0, kinds.indexOf('option') >= 0, kinds.indexOf('outcome') >= 0],
              optionCount:created.options.length,
              outcomeKinds:[outcomeA.kind, outcomeB.kind],
              reviewComplete:checklist.filter(function(item){ return item.complete; }).length,
              reviewTotal:checklist.length,
              inspectorChecklist:inspectorChecklistPresent,
              firstCommitCount:firstHistory.commits.length,
              commitCount:history.commits.length,
              chosenOptionId:history.chosenOptionId,
              expectedChosenOptionId:optionB.id,
              firstRationale:history.commits[0].rationale,
              firstSnapshot:firstOptionSnapshot && firstOptionSnapshot.content,
              secondSnapshot:secondOptionSnapshot && secondOptionSnapshot.content,
              rootStatus:rootNote && rootNote.status,
              alternativeStatuses:alternatives.map(function(note){ return note.status; }),
              chosenBadge:chosenCard && (chosenCard.querySelector('.tcNoteDecisionBadge') || {}).textContent,
              chosenClass:chosenCard && chosenCard.classList.contains('decisionChosen'),
              exportedVersion:exported.version,
              exportedCommits:exported.notes.filter(function(note){ return note.id === root.id; })[0].decisionRecord.commits.length,
              workbenchCommits:workbenchRoot.decisionRecord.commits.length,
              importedCommits:importedHistory.commits.length,
              commands:(window.STAGED_CMDS || []).slice()
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 180);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["decisionButton"], msg=json.dumps(result))
        self.assertEqual(result["semanticKinds"], [True, True, True], msg=json.dumps(result))
        self.assertEqual(result["optionCount"], 2, msg=json.dumps(result))
        self.assertEqual(result["outcomeKinds"], ["outcome", "outcome"], msg=json.dumps(result))
        self.assertEqual(result["reviewComplete"], result["reviewTotal"], msg=json.dumps(result))
        self.assertEqual(result["reviewTotal"], 7, msg=json.dumps(result))
        self.assertTrue(result["inspectorChecklist"], msg=json.dumps(result))
        self.assertEqual(result["firstCommitCount"], 1, msg=json.dumps(result))
        self.assertEqual(result["commitCount"], 2, msg=json.dumps(result))
        self.assertEqual(result["chosenOptionId"], result["expectedChosenOptionId"], msg=json.dumps(result))
        self.assertEqual(result["firstRationale"], "Best fit for the current constraints", msg=json.dumps(result))
        self.assertEqual(result["firstSnapshot"], "Option: Build the smaller workflow", msg=json.dumps(result))
        self.assertEqual(result["secondSnapshot"], "Option: Edited after the first commitment", msg=json.dumps(result))
        self.assertEqual(result["rootStatus"], "resolved", msg=json.dumps(result))
        self.assertEqual(result["alternativeStatuses"], ["open", "open"], msg=json.dumps(result))
        self.assertEqual(result["chosenBadge"], "Chosen", msg=json.dumps(result))
        self.assertTrue(result["chosenClass"], msg=json.dumps(result))
        self.assertEqual(result["exportedVersion"], 7, msg=json.dumps(result))
        self.assertEqual(result["exportedCommits"], 2, msg=json.dumps(result))
        self.assertEqual(result["workbenchCommits"], 2, msg=json.dumps(result))
        self.assertEqual(result["importedCommits"], 2, msg=json.dumps(result))
        self.assertEqual(result["commands"], [], msg=json.dumps(result))

    def test_canvas_inversion_analysis_builds_safeguards_and_survives_snapshots(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_INVERSION_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var api = window.KyanbasuNotes;
      var created = api.createDecisionMap(180, 300, 'Decisions');
      var root = created.root;
      var option = created.options[0];
      api.setContent(root.id, 'Decision: Choose a delivery approach\\nTarget outcome: Deliver a useful release\\nSuccess means: Used for one week\\nDecision needed by: Friday\\nReassess by: Next Friday');
      api.setContent(option.id, 'Option: Ship the smallest coherent workflow');
      api.selectNote(option.id);
      setTimeout(function(){
        var runButton = document.getElementById('inspectorInversionRun');
        if (!runButton) throw new Error('Run inversion control missing');
        runButton.click();
        setTimeout(function(){
          var inversionRoot = api.notes().filter(function(note){ return note.analysis && note.analysis.tool === 'inversion'; })[0];
          if (!inversionRoot) throw new Error('Inversion root missing');
          var failure = api.notes().filter(function(note){
            return note.kind === 'factor' && api.links().some(function(link){ return link.type === 'child' && link.from === inversionRoot.id && link.to === note.id; });
          })[0];
          if (!failure) throw new Error('Failure mode missing');
          var initial = api.inversionContext(inversionRoot.id);
          api.setContent(inversionRoot.id, 'INVERSION\\nDesired outcome: Deliver a useful release\\nAnalysed option: Ship the smallest coherent workflow\\nOpposite outcome: Release is abandoned and creates rework\\nHow could I deliberately cause the opposite outcome?');
          api.setContent(failure.id, 'Failure mode: Build too much before use\\nHow could this happen? Expand scope without feedback\\nEarly warning: No real use after three days\\nWithin my control: Yes');
          api.selectNote(failure.id);
          setTimeout(function(){
            var safeguardButton = document.getElementById('inspectorInversionAddSafeguard');
            if (!safeguardButton) throw new Error('Add safeguard control missing');
            safeguardButton.click();
            setTimeout(function(){
              var safeguard = api.notes().filter(function(note){
                return note.kind === 'action' && api.links().some(function(link){ return link.type === 'child' && link.from === failure.id && link.to === note.id; });
              })[0];
              if (!safeguard) throw new Error('Safeguard missing');
              api.setContent(safeguard.id, 'Prevent: Freeze scope\\nDetect early: Check use daily\\nRespond if it happens: Remove unused scope');
              var ready = api.inversionContext(inversionRoot.id);
              var siblingFailure = api.createSiblingNote(failure.id);
              var duplicateResult = api.runInversion(option.id);
              var inversionRoots = api.notes().filter(function(note){ return note.analysis && note.analysis.tool === 'inversion' && note.analysis.ownerId === option.id; });
              api.commitDecision(root.id, option.id, 'Inversion exposed a preventable scope risk');
              var history = api.decisionHistory(root.id);
              var snapshotInversion = history.commits[0].notes.filter(function(note){ return note.id === inversionRoot.id; })[0];
              var exported = api.exportData();
              var exportedInversion = exported.notes.filter(function(note){ return note.id === inversionRoot.id; })[0];
              window.KyanbasuWorkbenches.capture();
              var workbenches = window.KyanbasuWorkbenches.exportData();
              var workbenchInversion = workbenches.workbenches[0].notes.notes.filter(function(note){ return note.id === inversionRoot.id; })[0];
              api.importData(exported);
              setTimeout(function(){
                var importedInversion = api.notes().filter(function(note){ return note.id === inversionRoot.id; })[0];
                var importedContext = api.inversionContext(inversionRoot.id);
                var analysisCard = document.querySelector('.tcNoteNode[data-note-id="'+inversionRoot.id+'"]');
                var out = {
                  runControl:true,
                  initial:{
                    opposite:initial.oppositeRecorded,
                    failures:initial.failureCount,
                    missingSignals:initial.missingSignals,
                    unprotected:initial.unprotected,
                    complete:initial.complete
                  },
                  rootKind:inversionRoot.kind,
                  rootAnalysis:inversionRoot.analysis,
                  desiredOutcomeIncluded:inversionRoot.content.indexOf('Deliver a useful release') >= 0,
                  failureKind:failure.kind,
                  safeguardKind:safeguard.kind,
                  ready:ready,
                  siblingKind:siblingFailure.kind,
                  siblingTemplate:siblingFailure.content.indexOf('Failure mode:') === 0,
                  duplicateExisting:duplicateResult && duplicateResult.existing,
                  inversionRootCount:inversionRoots.length,
                  snapshotAnalysis:snapshotInversion && snapshotInversion.analysis,
                  exportedVersion:exported.version,
                  exportedAnalysis:exportedInversion && exportedInversion.analysis,
                  workbenchAnalysis:workbenchInversion && workbenchInversion.analysis,
                  importedAnalysis:importedInversion && importedInversion.analysis,
                  importedFailures:importedContext.failureCount,
                  analysisBadge:analysisCard && (analysisCard.querySelector('.tcNoteAnalysisBadge') || {}).textContent,
                  commits:history.commits.length,
                  commands:(window.STAGED_CMDS || []).slice()
                };
                var pre = document.createElement('pre');
                pre.id = 'e2e-out';
                pre.textContent = JSON.stringify(out);
                document.body.appendChild(pre);
              }, 180);
            }, 180);
          }, 180);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["runControl"], msg=json.dumps(result))
        self.assertEqual(result["initial"], {"opposite": False, "failures": 1, "missingSignals": 1, "unprotected": 1, "complete": False}, msg=json.dumps(result))
        self.assertEqual(result["rootKind"], "question", msg=json.dumps(result))
        self.assertEqual(result["rootAnalysis"]["tool"], "inversion", msg=json.dumps(result))
        self.assertEqual(result["rootAnalysis"]["role"], "root", msg=json.dumps(result))
        self.assertTrue(result["desiredOutcomeIncluded"], msg=json.dumps(result))
        self.assertEqual(result["failureKind"], "factor", msg=json.dumps(result))
        self.assertEqual(result["safeguardKind"], "action", msg=json.dumps(result))
        self.assertTrue(result["ready"]["complete"], msg=json.dumps(result))
        self.assertEqual(result["ready"]["missingSignals"], 0, msg=json.dumps(result))
        self.assertEqual(result["ready"]["unprotected"], 0, msg=json.dumps(result))
        self.assertEqual(result["siblingKind"], "factor", msg=json.dumps(result))
        self.assertTrue(result["siblingTemplate"], msg=json.dumps(result))
        self.assertTrue(result["duplicateExisting"], msg=json.dumps(result))
        self.assertEqual(result["inversionRootCount"], 1, msg=json.dumps(result))
        self.assertEqual(result["snapshotAnalysis"]["tool"], "inversion", msg=json.dumps(result))
        self.assertEqual(result["exportedVersion"], 7, msg=json.dumps(result))
        self.assertEqual(result["exportedAnalysis"]["tool"], "inversion", msg=json.dumps(result))
        self.assertEqual(result["workbenchAnalysis"]["tool"], "inversion", msg=json.dumps(result))
        self.assertEqual(result["importedAnalysis"]["tool"], "inversion", msg=json.dumps(result))
        self.assertEqual(result["importedFailures"], 2, msg=json.dumps(result))
        self.assertEqual(result["analysisBadge"], "Inversion", msg=json.dumps(result))
        self.assertEqual(result["commits"], 1, msg=json.dumps(result))
        self.assertEqual(result["commands"], [], msg=json.dumps(result))

    def test_canvas_consequence_analysis_branches_three_orders_and_round_trips(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_CONSEQUENCES_HARNESS">
window.addEventListener('error', function(ev){
  if (document.getElementById('e2e-out')) return;
  var pre = document.createElement('pre');
  pre.id = 'e2e-out';
  pre.textContent = 'ERR:' + (ev && ev.message ? ev.message : 'Unhandled browser error');
  document.body.appendChild(pre);
});
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var api = window.KyanbasuNotes;
      var created = api.createDecisionMap(180, 300, 'Decisions');
      var root = created.root;
      var option = created.options[0];
      api.setContent(option.id, 'Option: Launch a small weekly planning practice');
      api.selectNote(option.id);
      setTimeout(function(){
        var runButton = document.getElementById('inspectorConsequenceRun');
        if (!runButton) throw new Error('Explore consequences control missing');
        runButton.click();
        setTimeout(function(){
          var first = api.notes().filter(function(note){ return note.analysis && note.analysis.tool === 'consequences' && note.analysis.order === 1; })[0];
          if (!first) throw new Error('First-order consequence missing');
          var parallelControl = document.getElementById('inspectorConsequenceAddParallel');
          var nextControl = document.getElementById('inspectorConsequenceAddNext');
          api.setContent(first.id, '1st-order consequence: Weekly priorities become explicit\\nTime horizon: One week\\nLikelihood: 70%\\nPayoff / cost: Less drift\\nValue affected: Focus');
          var firstParallel = api.createParallelConsequence(first.id);
          var second = api.createNextConsequence(first.id);
          var secondParallel = api.createParallelConsequence(second.id);
          var third = api.createNextConsequence(second.id);
          var thirdParallel = api.createParallelConsequence(third.id);
          var context = api.consequenceContext(option.id);
          var thirdContext = api.consequenceContext(third.id);
          var duplicate = api.runConsequences(option.id);
          var afterDuplicate = api.consequenceContext(option.id);
          api.commitDecision(root.id, option.id, 'The delayed effects remain acceptable');
          var history = api.decisionHistory(root.id);
          var snapshotThird = history.commits[0].notes.filter(function(note){ return note.id === third.id; })[0];
          var exported = api.exportData();
          var exportedSecond = exported.notes.filter(function(note){ return note.id === second.id; })[0];
          window.KyanbasuWorkbenches.capture();
          var workbenches = window.KyanbasuWorkbenches.exportData();
          var workbenchThird = workbenches.workbenches[0].notes.notes.filter(function(note){ return note.id === third.id; })[0];
          api.importData(exported);
          setTimeout(function(){
            var imported = api.consequenceContext(option.id);
            var importedFirst = api.notes().filter(function(note){ return note.id === first.id; })[0];
            var analysisCard = document.querySelector('.tcNoteNode[data-note-id="'+first.id+'"]');
            var out = {
              runControl:true,
              branchControls:[!!parallelControl, !!nextControl],
              kinds:[first.kind, firstParallel.kind, second.kind, secondParallel.kind, third.kind, thirdParallel.kind],
              orders:[first.analysis.order, firstParallel.analysis.order, second.analysis.order, secondParallel.analysis.order, third.analysis.order, thirdParallel.analysis.order],
              sharedOwner:[first, firstParallel, second, secondParallel, third, thirdParallel].every(function(note){ return note.analysis.ownerId === option.id; }),
              sharedRun:[first, firstParallel, second, secondParallel, third, thirdParallel].every(function(note){ return note.analysis.runId === first.analysis.runId; }),
              templates:[firstParallel.content.indexOf('1st-order consequence:') === 0, second.content.indexOf('2nd-order consequence:') === 0, third.content.indexOf('3rd-order consequence:') === 0],
              counts:context.counts,
              earlyStops:context.earlyStops,
              complete:context.complete,
              thirdCanAddNext:thirdContext.canAddNext,
              duplicateExisting:duplicate && duplicate.existing,
              countAfterDuplicate:afterDuplicate.total,
              snapshotAnalysis:snapshotThird && snapshotThird.analysis,
              exportedVersion:exported.version,
              exportedAnalysis:exportedSecond && exportedSecond.analysis,
              workbenchAnalysis:workbenchThird && workbenchThird.analysis,
              importedAnalysis:importedFirst && importedFirst.analysis,
              importedCounts:imported.counts,
              importedEarlyStops:imported.earlyStops,
              analysisBadge:analysisCard && (analysisCard.querySelector('.tcNoteAnalysisBadge') || {}).textContent,
              commands:(window.STAGED_CMDS || []).slice()
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 180);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["runControl"], msg=json.dumps(result))
        self.assertEqual(result["branchControls"], [True, True], msg=json.dumps(result))
        self.assertEqual(result["kinds"], ["outcome"] * 6, msg=json.dumps(result))
        self.assertEqual(result["orders"], [1, 1, 2, 2, 3, 3], msg=json.dumps(result))
        self.assertTrue(result["sharedOwner"], msg=json.dumps(result))
        self.assertTrue(result["sharedRun"], msg=json.dumps(result))
        self.assertEqual(result["templates"], [True, True, True], msg=json.dumps(result))
        self.assertEqual(result["counts"], {"1": 2, "2": 2, "3": 2}, msg=json.dumps(result))
        self.assertEqual(result["earlyStops"], 2, msg=json.dumps(result))
        self.assertFalse(result["complete"], msg=json.dumps(result))
        self.assertFalse(result["thirdCanAddNext"], msg=json.dumps(result))
        self.assertTrue(result["duplicateExisting"], msg=json.dumps(result))
        self.assertEqual(result["countAfterDuplicate"], 6, msg=json.dumps(result))
        self.assertEqual(result["snapshotAnalysis"]["order"], 3, msg=json.dumps(result))
        self.assertEqual(result["exportedVersion"], 7, msg=json.dumps(result))
        self.assertEqual(result["exportedAnalysis"]["order"], 2, msg=json.dumps(result))
        self.assertEqual(result["workbenchAnalysis"]["order"], 3, msg=json.dumps(result))
        self.assertEqual(result["importedAnalysis"]["order"], 1, msg=json.dumps(result))
        self.assertEqual(result["importedCounts"], {"1": 2, "2": 2, "3": 2}, msg=json.dumps(result))
        self.assertEqual(result["importedEarlyStops"], 2, msg=json.dumps(result))
        self.assertEqual(result["analysisBadge"], "1st order", msg=json.dumps(result))
        self.assertEqual(result["commands"], [], msg=json.dumps(result))

    def test_canvas_notes_selects_and_unlinks_canvas_link(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_UNLINK_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 220, "Plan", "");
      var b = window.KyanbasuNotes.createNote(560, 250, "Step 1", "");
      window.KyanbasuNotes.linkNotes(a.id, b.id);
      setTimeout(function(){
        var path = document.querySelector('#tcNoteLinksLayer path.tcNoteLinkHit');
        path.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
        setTimeout(function(){
          var selectedBefore = document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length;
          var toolbarBefore = !!document.getElementById('tcNoteLinkToolbar');
          var selectedNotesBefore = document.querySelectorAll('.tcNoteNode.selected').length;
          document.querySelector('#tcNoteLinkToolbar [data-link-unlink]').click();
          setTimeout(function(){
            var out = {
              selectedBefore: selectedBefore,
              toolbarBefore: toolbarBefore,
              selectedNotesBefore: selectedNotesBefore,
              linksAfter: window.KyanbasuNotes.links().length,
              pathsAfter: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink').length,
              toolbarAfter: !!document.getElementById('tcNoteLinkToolbar'),
              console: (document.getElementById('consoleText') || {}).value || ""
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 80);
        }, 80);
      }, 100);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["selectedBefore"], 1, msg=json.dumps(result))
        self.assertTrue(result["toolbarBefore"], msg=json.dumps(result))
        self.assertEqual(result["selectedNotesBefore"], 0, msg=json.dumps(result))
        self.assertEqual(result["linksAfter"], 0, msg=json.dumps(result))
        self.assertEqual(result["pathsAfter"], 0, msg=json.dumps(result))
        self.assertFalse(result["toolbarAfter"], msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_notes_drag_handle_creates_link(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_DRAG_LINK_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 220, "Plan", "");
      var b = window.KyanbasuNotes.createNote(620, 250, "Step 1", "");
      window.KyanbasuNotes.selectNote(a.id);
      setTimeout(function(){
        var handle = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"] .tcNoteLinkHandle');
        var target = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
        var hr = handle.getBoundingClientRect();
        var tr = target.getBoundingClientRect();
        handle.dispatchEvent(new MouseEvent('mousedown', {
          bubbles:true, cancelable:true, button:0,
          clientX:hr.left + hr.width / 2,
          clientY:hr.top + hr.height / 2
        }));
        document.dispatchEvent(new MouseEvent('mousemove', {
          bubbles:true, cancelable:true,
          clientX:tr.left + tr.width / 2,
          clientY:tr.top + tr.height / 2
        }));
        target.dispatchEvent(new MouseEvent('mouseup', {
          bubbles:true, cancelable:true, button:0,
          clientX:tr.left + tr.width / 2,
          clientY:tr.top + tr.height / 2
        }));
        setTimeout(function(){
          var links = window.KyanbasuNotes.links();
          var out = {
            links: links.length,
            from: links[0] && links[0].from,
            to: links[0] && links[0].to,
            type: links[0] && links[0].type,
            selectedPath: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length,
            previewPaths: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLinkPreview').length,
            toolbar: !!document.getElementById('tcNoteLinkToolbar'),
            selectedNotes: document.querySelectorAll('.tcNoteNode.selected').length,
            console: (document.getElementById('consoleText') || {}).value || ""
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 100);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["links"], 1, msg=json.dumps(result))
        self.assertEqual(result["type"], "manual", msg=json.dumps(result))
        self.assertTrue(result["from"], msg=json.dumps(result))
        self.assertTrue(result["to"], msg=json.dumps(result))
        self.assertEqual(result["selectedPath"], 1, msg=json.dumps(result))
        self.assertEqual(result["previewPaths"], 0, msg=json.dumps(result))
        self.assertTrue(result["toolbar"], msg=json.dumps(result))
        self.assertEqual(result["selectedNotes"], 0, msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_notes_relinks_selected_link_endpoint(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_RELINK_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 220, "Plan", "");
      var b = window.KyanbasuNotes.createNote(620, 250, "Step 1", "");
      var c = window.KyanbasuNotes.createNote(620, 430, "Step 2", "");
      window.KyanbasuNotes.linkNotes(a.id, b.id);
      setTimeout(function(){
        var path = document.querySelector('#tcNoteLinksLayer path.tcNoteLinkHit');
        path.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
        setTimeout(function(){
          var endpoint = document.querySelector('.tcNoteLinkEndpoint.to');
          var target = document.querySelector('.tcNoteNode[data-note-id="'+c.id+'"]');
          var er = endpoint.getBoundingClientRect();
          var tr = target.getBoundingClientRect();
          endpoint.dispatchEvent(new MouseEvent('mousedown', {
            bubbles:true, cancelable:true, button:0,
            clientX:er.left + er.width / 2,
            clientY:er.top + er.height / 2
          }));
          document.dispatchEvent(new MouseEvent('mousemove', {
            bubbles:true, cancelable:true,
            clientX:tr.left + tr.width / 2,
            clientY:tr.top + tr.height / 2
          }));
          target.dispatchEvent(new MouseEvent('mouseup', {
            bubbles:true, cancelable:true, button:0,
            clientX:tr.left + tr.width / 2,
            clientY:tr.top + tr.height / 2
          }));
          setTimeout(function(){
            var links = window.KyanbasuNotes.links();
            var out = {
              links: links.length,
              fromUnchanged: links[0] && links[0].from === a.id,
              toChanged: links[0] && links[0].to === c.id,
              oldTargetRemoved: !links.some(function(l){ return l.to === b.id; }),
              selectedPath: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length,
              endpoints: document.querySelectorAll('.tcNoteLinkEndpoint').length,
              previewPaths: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLinkPreview').length,
              console: (document.getElementById('consoleText') || {}).value || ""
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 100);
        }, 80);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["links"], 1, msg=json.dumps(result))
        self.assertTrue(result["fromUnchanged"], msg=json.dumps(result))
        self.assertTrue(result["toChanged"], msg=json.dumps(result))
        self.assertTrue(result["oldTargetRemoved"], msg=json.dumps(result))
        self.assertEqual(result["selectedPath"], 1, msg=json.dumps(result))
        self.assertEqual(result["endpoints"], 2, msg=json.dumps(result))
        self.assertEqual(result["previewPaths"], 0, msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_notes_creates_edits_searches_and_exports_semantic_links(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_SEMANTIC_LINK_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var source = window.KyanbasuNotes.createNote(220, 240, 'Profiling evidence', '');
      var target = window.KyanbasuNotes.createNote(620, 240, 'Disable idle observers', '');
      window.KyanbasuNotes.selectNote(source.id);
      window.KyanbasuNotes.selectNote(target.id, true);
      setTimeout(function(){
        var createType = document.querySelector('.tcNoteLinkCreateType');
        var createOptions = Array.prototype.slice.call(createType.options).map(function(option){ return option.value; });
        createType.value = 'supports';
        document.querySelector('.tcNoteLinkPrimary').click();
        setTimeout(function(){
          var beforeLink = window.KyanbasuNotes.links()[0];
          var baseSelect = document.getElementById('inspectorNoteLinkType');
          var before = {
            type:beforeLink && beforeLink.type,
            createOptions:createOptions,
            floatingType:(document.querySelector('#tcNoteLinkInspector .tcNoteLinkTypeSelect') || {}).value || '',
            inspectorType:baseSelect && baseSelect.value,
            supportsSearch:window.KyanbasuNotes.searchNotes('supports'),
            supportedBySearch:window.KyanbasuNotes.searchNotes('supported by'),
            pathType:(document.querySelector('#tcNoteLinksLayer .tcNoteLink') || {}).getAttribute('data-type') || ''
          };
          baseSelect.value = 'challenges';
          baseSelect.dispatchEvent(new Event('change', {bubbles:true}));
          setTimeout(function(){
            var link = window.KyanbasuNotes.links()[0];
            var path = document.querySelector('#tcNoteLinksLayer .tcNoteLink');
            var exported = window.KyanbasuNotes.exportData();
            var out = {
              before:before,
              type:link && link.type,
              pathType:path && path.getAttribute('data-type'),
              pathTitle:(path && path.querySelector('title') || {}).textContent || '',
              animationName:path ? getComputedStyle(path).animationName : '',
              toolbarType:(document.querySelector('.tcNoteLinkToolbarType') || {}).textContent || '',
              exportedVersion:exported.version,
              exportedType:exported.links[0] && exported.links[0].type,
              relationLabel:window.KyanbasuNotesCore.relationLabel('challenges', false),
              inverseLabel:window.KyanbasuNotesCore.relationLabel('challenges', true)
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 140);
        }, 140);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["before"]["type"], "supports")
        self.assertNotIn("child", result["before"]["createOptions"])
        self.assertEqual(result["before"]["floatingType"], "supports")
        self.assertEqual(result["before"]["inspectorType"], "supports")
        self.assertEqual(len(result["before"]["supportsSearch"]), 1)
        self.assertEqual(len(result["before"]["supportedBySearch"]), 1)
        self.assertEqual(result["before"]["pathType"], "supports")
        self.assertEqual(result["type"], "challenges")
        self.assertEqual(result["pathType"], "challenges")
        self.assertEqual(result["pathTitle"], "Challenges")
        self.assertEqual(result["animationName"], "none")
        self.assertEqual(result["toolbarType"], "Challenges")
        self.assertEqual(result["exportedVersion"], 7)
        self.assertEqual(result["exportedType"], "challenges")
        self.assertEqual(result["relationLabel"], "Challenges")
        self.assertEqual(result["inverseLabel"], "Challenged by")

    def test_canvas_note_link_mouse_sequence_opens_selection_inspector(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTE_LINK_MOUSE_SELECTION_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var from = KyanbasuNotes.createNote(180, 220, 'Source note', '', 'Research', {skipAutoLayout:true});
      var to = KyanbasuNotes.createNote(620, 260, 'Target note', '', 'Planning', {skipAutoLayout:true});
      KyanbasuNotes.linkNotes(from.id, to.id, 'supports');
      var path = document.querySelector('#tcNoteLinksLayer path.tcNoteLinkHit');
      path.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0}));
      path.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0}));
      path.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, button:0}));
      setTimeout(function(){
        var out = {
          selection:KyanbasuNotes.selectionSnapshot(),
          inspectorTitle:(document.getElementById('inspectorTitle') || {}).textContent || '',
          annotationEditor:!!document.getElementById('inspectorNoteLinkAnnotationText'),
          selectedPath:document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 100);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["selection"]["kind"], "link", msg=json.dumps(result))
        self.assertEqual(result["inspectorTitle"], "Note link selected", msg=json.dumps(result))
        self.assertTrue(result["annotationEditor"], msg=json.dumps(result))
        self.assertEqual(result["selectedPath"], 1, msg=json.dumps(result))

    def test_canvas_note_link_annotations_render_edit_round_trip_and_clear(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTE_LINK_ANNOTATION_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var from = KyanbasuNotes.createNote(180, 220, 'Evidence', '', 'Research', {skipAutoLayout:true});
      var to = KyanbasuNotes.createNote(620, 260, 'Decision', '', 'Planning', {skipAutoLayout:true});
      KyanbasuNotes.linkNotes(from.id, to.id, 'supports');
      var link = KyanbasuNotes.links()[0];
      var key = [link.from, link.to, link.type].join('::');
      KyanbasuNotes.setLinkAnnotation(key, {kind:'question', text:'Is this evidence current?'});
      var badge = document.querySelector('#tcNoteLinksLayer .tcNoteLinkAnnotation');
      var initial = {
        badges:document.querySelectorAll('#tcNoteLinksLayer .tcNoteLinkAnnotation').length,
        triangles:document.querySelectorAll('#tcNoteLinksLayer .tcNoteLinkAnnotationTriangle').length,
        kind:badge && badge.getAttribute('data-kind'),
        icon:(badge && badge.querySelector('.tcNoteLinkAnnotationIcon') || {}).textContent || '',
        label:(badge && badge.querySelector('.tcNoteLinkAnnotationLabel') || {}).textContent || ''
      };
      badge.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
      setTimeout(function(){
        var kindInput = document.getElementById('inspectorNoteLinkAnnotationKind');
        var textInput = document.getElementById('inspectorNoteLinkAnnotationText');
        textInput.value = 'Only if validation passes';
        kindInput.value = 'condition';
        kindInput.dispatchEvent(new Event('change', {bubbles:true}));
        setTimeout(function(){
          var exported = KyanbasuNotes.exportData();
          var exportedAnnotation = exported.links[0].annotation;
          KyanbasuNotes.importData(exported);
          var importedBadge = document.querySelector('#tcNoteLinksLayer .tcNoteLinkAnnotation');
          importedBadge.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
          setTimeout(function(){
            var clear = document.getElementById('inspectorNoteLinkAnnotationClear');
            clear.click();
            setTimeout(function(){
              var out = {
                initial:initial,
                selectedKind:KyanbasuNotes.selectionSnapshot().kind,
                exportedVersion:exported.version,
                exportedAnnotation:exportedAnnotation,
                importedKind:importedBadge.getAttribute('data-kind'),
                importedLabel:(importedBadge.querySelector('.tcNoteLinkAnnotationLabel') || {}).textContent || '',
                badgesAfterClear:document.querySelectorAll('#tcNoteLinksLayer .tcNoteLinkAnnotation').length,
                annotationAfterClear:KyanbasuNotes.links()[0].annotation || null,
                exportedHasAnnotation:Object.prototype.hasOwnProperty.call(KyanbasuNotes.exportData().links[0], 'annotation')
              };
              var pre = document.createElement('pre');
              pre.id = 'e2e-out';
              pre.textContent = JSON.stringify(out);
              document.body.appendChild(pre);
            }, 80);
          }, 80);
        }, 80);
      }, 80);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["initial"]["badges"], 1, msg=json.dumps(result))
        self.assertEqual(result["initial"]["triangles"], 1, msg=json.dumps(result))
        self.assertEqual(result["initial"]["kind"], "question", msg=json.dumps(result))
        self.assertEqual(result["initial"]["icon"], "?", msg=json.dumps(result))
        self.assertIn("evidence current", result["initial"]["label"], msg=json.dumps(result))
        self.assertEqual(result["selectedKind"], "link", msg=json.dumps(result))
        self.assertEqual(result["exportedVersion"], 7, msg=json.dumps(result))
        self.assertEqual(result["exportedAnnotation"], {"kind": "condition", "text": "Only if validation passes"}, msg=json.dumps(result))
        self.assertEqual(result["importedKind"], "condition", msg=json.dumps(result))
        self.assertIn("validation passes", result["importedLabel"], msg=json.dumps(result))
        self.assertEqual(result["badgesAfterClear"], 0, msg=json.dumps(result))
        self.assertIsNone(result["annotationAfterClear"], msg=json.dumps(result))
        self.assertFalse(result["exportedHasAnnotation"], msg=json.dumps(result))

    def test_canvas_note_link_inline_annotation_interactions(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTE_LINK_INLINE_ANNOTATION_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var from = KyanbasuNotes.createNote(180, 220, 'Source', '', 'Research', {skipAutoLayout:true});
      var to = KyanbasuNotes.createNote(620, 260, 'Target', '', 'Planning', {skipAutoLayout:true});
      KyanbasuNotes.linkNotes(from.id, to.id, 'supports');
      KyanbasuNotes.clearSelection();
      var hit = document.querySelector('#tcNoteLinksLayer path.tcNoteLinkHit');
      var visual = document.querySelector('#tcNoteLinksLayer path.tcNoteLink');
      var add = document.querySelector('#tcNoteLinksLayer .tcNoteLinkAnnotationAdd');
      var hitStyle = getComputedStyle(hit);
      var visualStyle = getComputedStyle(visual);
      hit.dispatchEvent(new MouseEvent('mouseenter', {bubbles:false, cancelable:true}));
      var hover = {
        hitStroke:parseFloat(hitStyle.strokeWidth || '0'),
        hitPointerEvents:hitStyle.pointerEvents,
        visualPointerEvents:visualStyle.pointerEvents,
        visualHovered:visual.classList.contains('hovered'),
        addHovered:add.classList.contains('hovered')
      };
      add.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, button:0}));
      setTimeout(function(){
        var editor = document.getElementById('tcNoteLinkAnnotationEditor');
        var kind = editor && editor.querySelector('.tcNoteLinkAnnotationKind');
        var text = editor && editor.querySelector('.tcNoteLinkAnnotationText');
        kind.value = 'question';
        text.value = 'What evidence supports this?';
        text.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
        setTimeout(function(){
          var saved = KyanbasuNotes.links()[0].annotation;
          var badge = document.querySelector('#tcNoteLinksLayer .tcNoteLinkAnnotation');
          var inspectorText = document.getElementById('inspectorNoteLinkAnnotationText');
          badge.dispatchEvent(new MouseEvent('dblclick', {bubbles:true, cancelable:true, button:0, detail:2}));
          setTimeout(function(){
            var editEditor = document.getElementById('tcNoteLinkAnnotationEditor');
            var editText = editEditor && editEditor.querySelector('.tcNoteLinkAnnotationText');
            editText.value = 'This edit should be cancelled';
            editText.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true, cancelable:true}));
            setTimeout(function(){
              var current = KyanbasuNotes.links()[0].annotation;
              var active = document.activeElement;
              var out = {
                hover:hover,
                midpointAddExists:!!add,
                saved:saved,
                badgeKind:badge && badge.getAttribute('data-kind'),
                inspectorText:inspectorText && inspectorText.value,
                editorClosed:!document.getElementById('tcNoteLinkAnnotationEditor'),
                cancelPreserved:current && current.text,
                focusReturned:!!active && active.classList.contains('tcNoteLinkHit'),
                selected:KyanbasuNotes.selectionSnapshot().kind,
                console:(document.getElementById('consoleText') || {}).value || ''
              };
              var pre = document.createElement('pre');
              pre.id = 'e2e-out';
              pre.textContent = JSON.stringify(out);
              document.body.appendChild(pre);
            }, 80);
          }, 60);
        }, 100);
      }, 60);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertGreaterEqual(result["hover"]["hitStroke"], 14, msg=json.dumps(result))
        self.assertEqual(result["hover"]["hitPointerEvents"], "stroke", msg=json.dumps(result))
        self.assertEqual(result["hover"]["visualPointerEvents"], "none", msg=json.dumps(result))
        self.assertTrue(result["hover"]["visualHovered"], msg=json.dumps(result))
        self.assertTrue(result["hover"]["addHovered"], msg=json.dumps(result))
        self.assertTrue(result["midpointAddExists"], msg=json.dumps(result))
        self.assertEqual(result["saved"], {"kind": "question", "text": "What evidence supports this?"}, msg=json.dumps(result))
        self.assertEqual(result["badgeKind"], "question", msg=json.dumps(result))
        self.assertEqual(result["inspectorText"], "What evidence supports this?", msg=json.dumps(result))
        self.assertTrue(result["editorClosed"], msg=json.dumps(result))
        self.assertEqual(result["cancelPreserved"], "What evidence supports this?", msg=json.dumps(result))
        self.assertTrue(result["focusReturned"], msg=json.dumps(result))
        self.assertEqual(result["selected"], "link", msg=json.dumps(result))
        self.assertEqual(result["console"], "")

    def test_canvas_note_link_annotations_are_zoom_aware_and_searchable(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTE_LINK_ANNOTATION_DISCOVERY_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var source = KyanbasuNotes.createNote(180, 220, 'Deployment evidence', '', 'Research', {skipAutoLayout:true});
      var target = KyanbasuNotes.createNote(620, 260, 'Release decision', '', 'Planning', {skipAutoLayout:true});
      var unrelated = KyanbasuNotes.createNote(980, 260, 'Meeting notes', '', 'Planning', {skipAutoLayout:true});
      KyanbasuNotes.linkNotes(source.id, target.id, 'supports');
      var link = KyanbasuNotes.links()[0];
      var key = [link.from, link.to, link.type].join('::');
      KyanbasuNotes.setLinkAnnotation(key, {kind:'question', text:'What deployment risk remains?'});
      var textMatches = KyanbasuNotes.searchNotes('deployment risk');
      var kindMatches = KyanbasuNotes.searchNotes('annotation:question');
      var fieldMatches = KyanbasuNotes.searchNotes('annotation:"deployment risk"');
      var hasMatches = KyanbasuNotes.searchNotes('has:annotations');
      var outline = KyanbasuNotes.outline();
      var outlineById = {};
      function collect(items){
        (items || []).forEach(function(item){ outlineById[item.id] = item; collect(item.children); });
      }
      collect(outline);
      var zoom = document.getElementById('zoom');
      zoom.value = '70';
      zoom.dispatchEvent(new Event('input', {bubbles:true}));
      var layer = document.getElementById('tcNoteLinksLayer');
      var triangle = document.querySelector('.tcNoteLinkAnnotationTriangle');
      var labelBg = document.querySelector('.tcNoteLinkAnnotationLabelBg');
      var label = document.querySelector('.tcNoteLinkAnnotationLabel');
      var compact = {
        detail:layer.getAttribute('data-annotation-detail'),
        triangle:getComputedStyle(triangle).display,
        labelBg:getComputedStyle(labelBg).display,
        label:getComputedStyle(label).display
      };
      zoom.value = '100';
      zoom.dispatchEvent(new Event('input', {bubbles:true}));
      var full = {
        detail:layer.getAttribute('data-annotation-detail'),
        labelBg:getComputedStyle(labelBg).display,
        label:getComputedStyle(label).display
      };
      var input = document.getElementById('noteSearchInput');
      input.value = 'deployment risk';
      input.dispatchEvent(new Event('input', {bubbles:true}));
      if (typeof renderViewer === 'function') renderViewer();
      setTimeout(function(){
        var resultContexts = Array.from(document.querySelectorAll('#noteSearchResults .tcNoteSearchAnnotation')).map(function(el){ return el.textContent; });
        var viewerChips = Array.from(document.querySelectorAll('#viewerStage .viewerNoteSemantic.annotation')).map(function(el){ return el.textContent; });
        var out = {
          source:source.id,
          target:target.id,
          unrelated:unrelated.id,
          textMatches:textMatches,
          kindMatches:kindMatches,
          fieldMatches:fieldMatches,
          hasMatches:hasMatches,
          sourceAnnotations:(outlineById[source.id] && outlineById[source.id].annotations) || [],
          targetAnnotations:(outlineById[target.id] && outlineById[target.id].annotations) || [],
          compact:compact,
          full:full,
          resultContexts:resultContexts,
          viewerChips:viewerChips,
          console:(document.getElementById('consoleText') || {}).value || ''
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 100);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        expected_ids = {result["source"], result["target"]}
        self.assertEqual(set(result["textMatches"]), expected_ids, msg=json.dumps(result))
        self.assertEqual(set(result["kindMatches"]), expected_ids, msg=json.dumps(result))
        self.assertEqual(set(result["fieldMatches"]), expected_ids, msg=json.dumps(result))
        self.assertEqual(set(result["hasMatches"]), expected_ids, msg=json.dumps(result))
        self.assertNotIn(result["unrelated"], result["textMatches"], msg=json.dumps(result))
        self.assertEqual(result["sourceAnnotations"][0]["direction"], "outgoing", msg=json.dumps(result))
        self.assertEqual(result["targetAnnotations"][0]["direction"], "incoming", msg=json.dumps(result))
        self.assertEqual(result["compact"]["detail"], "compact", msg=json.dumps(result))
        self.assertNotEqual(result["compact"]["triangle"], "none", msg=json.dumps(result))
        self.assertEqual(result["compact"]["labelBg"], "none", msg=json.dumps(result))
        self.assertEqual(result["compact"]["label"], "none", msg=json.dumps(result))
        self.assertEqual(result["full"]["detail"], "full", msg=json.dumps(result))
        self.assertNotEqual(result["full"]["labelBg"], "none", msg=json.dumps(result))
        self.assertNotEqual(result["full"]["label"], "none", msg=json.dumps(result))
        self.assertEqual(len(result["resultContexts"]), 2, msg=json.dumps(result))
        self.assertTrue(all("deployment risk" in text.lower() for text in result["resultContexts"]), msg=json.dumps(result))
        self.assertEqual(len(result["viewerChips"]), 2, msg=json.dumps(result))
        self.assertTrue(all("deployment risk" in text.lower() for text in result["viewerChips"]), msg=json.dumps(result))
        self.assertEqual(result["console"], "")

    def test_canvas_notes_link_inspector_manages_selected_note_links(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_LINK_INSPECTOR_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 220, "Plan", "");
      var b = window.KyanbasuNotes.createNote(620, 250, "Step 1", "");
      window.KyanbasuNotes.linkNotes(a.id, b.id);
      window.KyanbasuNotes.selectNote(a.id);
      setTimeout(function(){
        var panel = document.getElementById('tcNoteLinkInspector');
        var relink = panel && panel.querySelector('.tcNoteLinkMini:not(.danger)');
        var remove = panel && panel.querySelector('.tcNoteLinkMini.danger');
        var before = {
          visible: !!panel && !panel.hidden,
          rows: panel ? panel.querySelectorAll('.tcNoteLinkInspectorRow').length : 0,
          labels: panel ? panel.textContent : "",
          selectedPaths: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length
        };
        relink.click();
        setTimeout(function(){
          var selectedAfterRelink = document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length;
          var endpointsAfterRelink = document.querySelectorAll('.tcNoteLinkEndpoint').length;
          remove.click();
          setTimeout(function(){
            var out = {
              visible: before.visible,
              rows: before.rows,
              labels: before.labels,
              selectedBefore: before.selectedPaths,
              selectedAfterRelink: selectedAfterRelink,
              endpointsAfterRelink: endpointsAfterRelink,
              linksAfterRemove: window.KyanbasuNotes.links().length,
              panelAfterRemove: !!panel && !panel.hidden,
              console: (document.getElementById('consoleText') || {}).value || ""
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 80);
        }, 80);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["visible"], msg=json.dumps(result))
        self.assertEqual(result["rows"], 1, msg=json.dumps(result))
        self.assertIn("Step 1", result["labels"], msg=json.dumps(result))
        self.assertEqual(result["selectedBefore"], 0, msg=json.dumps(result))
        self.assertEqual(result["selectedAfterRelink"], 1, msg=json.dumps(result))
        self.assertEqual(result["endpointsAfterRelink"], 2, msg=json.dumps(result))
        self.assertEqual(result["linksAfterRemove"], 0, msg=json.dumps(result))
        self.assertFalse(result["panelAfterRemove"], msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_notes_link_inspector_links_two_selected_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_LINK_SELECTED_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 220, "Plan", "");
      var b = window.KyanbasuNotes.createNote(620, 250, "Step 1", "");
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      setTimeout(function(){
        var panel = document.getElementById('tcNoteLinkInspector');
        var button = panel && panel.querySelector('.tcNoteLinkPrimary');
        var before = {
          visible: !!panel && !panel.hidden,
          selected: window.KyanbasuNotes.selectedNotes().length,
          picked: panel ? panel.querySelectorAll('.tcNoteLinkPicked').length : 0,
          text: panel ? panel.textContent : "",
          disabled: button ? button.disabled : true
        };
        button.click();
        setTimeout(function(){
          var links = window.KyanbasuNotes.links();
          var out = {
            visible: before.visible,
            selected: before.selected,
            picked: before.picked,
            text: before.text,
            disabled: before.disabled,
            links: links.length,
            fromA: links[0] && links[0].from === a.id,
            toB: links[0] && links[0].to === b.id,
            selectedAfter: window.KyanbasuNotes.selectedNotes().length,
            selectedPath: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink.selected').length,
            console: (document.getElementById('consoleText') || {}).value || ""
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 100);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["visible"], msg=json.dumps(result))
        self.assertEqual(result["selected"], 2, msg=json.dumps(result))
        self.assertEqual(result["picked"], 2, msg=json.dumps(result))
        self.assertIn("Link selected notes", result["text"], msg=json.dumps(result))
        self.assertFalse(result["disabled"], msg=json.dumps(result))
        self.assertEqual(result["links"], 1, msg=json.dumps(result))
        self.assertTrue(result["fromA"], msg=json.dumps(result))
        self.assertTrue(result["toB"], msg=json.dumps(result))
        self.assertEqual(result["selectedAfter"], 0, msg=json.dumps(result))
        self.assertEqual(result["selectedPath"], 1, msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_note_mode_click_places_note_at_clicked_position(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_CLICK_PLACEMENT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.createNote(760, 220, "Existing", "", "Planning");
      var stage = document.getElementById('builderStage');
      var noteBtn = document.getElementById('noteModeBtn');
      var sr = stage.getBoundingClientRect();
      var target = {x:260, y:360};
      noteBtn.click();
      stage.dispatchEvent(new MouseEvent('click', {
        bubbles:true,
        cancelable:true,
        clientX:sr.left + target.x,
        clientY:sr.top + target.y
      }));
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var created = notes.filter(function(n){ return n.content === 'New note'; })[0];
        var out = {
          notes: notes.length,
          x: created && created.x,
          y: created && created.y,
          nearClick: !!(created && Math.abs(created.x - target.x) <= 8 && Math.abs(created.y - target.y) <= 8),
          notFarRight: !!(created && created.x < target.x + 80)
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 140);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["notes"], 2)
        self.assertTrue(result["nearClick"], msg=json.dumps(result))
        self.assertTrue(result["notFarRight"], msg=json.dumps(result))

    def test_canvas_notes_imports_taskcanvas_export_and_reexports_as_kyanbasu(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_IMPORT_EXPORT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var imported = {
        kind: 'taskcanvas.notes',
        version: 1,
        notes: [
          {id:'root-note', x:180, y:220, title:'Imported root', body:'Legacy body', bucket:'Planning', collapsed:true},
          {id:'child-note', x:480, y:220, content:'Imported child', bucket:'Execution', collapsed:false}
        ],
        links: [
          {from:'root-note', to:'child-note', type:'child'},
          {from:'missing-note', to:'child-note', type:'manual'}
        ]
      };
      var result = window.KyanbasuNotes.importJSON(JSON.stringify(imported));
      var exported = JSON.parse(window.KyanbasuNotes.exportJSON());
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var out = {
          importButton: !!document.getElementById('noteImportBtn'),
          exportButton: !!document.getElementById('noteExportBtn'),
          resultNotes: result.notes,
          resultLinks: result.links,
          exportedKind: exported.kind,
          exportedVersion: exported.version,
          exportedNotes: exported.notes.length,
          exportedLinks: exported.links.length,
          firstContent: notes[0] && notes[0].content,
          firstBucket: notes[0] && notes[0].bucket,
          firstCollapsed: notes[0] && notes[0].collapsed,
          exportedFirstBucket: exported.notes[0] && exported.notes[0].bucket,
          exportedSecondBucket: exported.notes[1] && exported.notes[1].bucket,
          visibleNotes: Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length,
          savedKeys: Object.keys(localStorage).filter(function(k){ return k.indexOf('kyanbasu:workspace:v1:') === 0; }).length,
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["importButton"])
        self.assertTrue(result["exportButton"])
        self.assertEqual(result["resultNotes"], 2)
        self.assertEqual(result["resultLinks"], 1)
        self.assertEqual(result["exportedKind"], "kyanbasu.notes")
        self.assertEqual(result["exportedVersion"], 7)
        self.assertEqual(result["exportedNotes"], 2)
        self.assertEqual(result["exportedLinks"], 1)
        self.assertEqual(result["firstContent"], "Imported root\nLegacy body")
        self.assertEqual(result["firstBucket"], "Planning")
        self.assertEqual(result["exportedFirstBucket"], "Planning")
        self.assertEqual(result["exportedSecondBucket"], "Execution")
        self.assertTrue(result["firstCollapsed"])
        self.assertEqual(result["visibleNotes"], 1)
        self.assertGreaterEqual(result["savedKeys"], 1)
        self.assertEqual(result["console"], "")

    def test_canvas_notes_groups_visible_notes_by_bucket(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKETS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 220, "One", "", "Planning");
      var b = window.KyanbasuNotes.createNote(480, 260, "Two", "", "Planning");
      var c = window.KyanbasuNotes.createNote(820, 240, "Three", "", "Delivery");
      var initialBucketCount = document.querySelectorAll('.tcNoteBucket').length;
      var bucketLabels = Array.prototype.slice.call(document.querySelectorAll('.tcNoteBucketTitle')).map(function(el){ return el.textContent; });
      var noteLabel = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"] .tcNoteBucketLabel');
      window.KyanbasuNotes.setBucket(c.id, "Planning");
      setTimeout(function(){
        var out = {
          bucketCount: initialBucketCount,
          bucketLabels: bucketLabels,
          noteBucketLabel: noteLabel ? noteLabel.textContent : "",
          mergedBucketCount: document.querySelectorAll('.tcNoteBucket').length,
          mergedBucketLabel: (document.querySelector('.tcNoteBucketTitle') || {}).textContent || "",
          mergedBucketNotes: Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){
            return el.getAttribute('data-bucket') === 'Planning';
          }).length
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["bucketCount"], 2)
        self.assertIn("Planning", result["bucketLabels"])
        self.assertIn("Delivery", result["bucketLabels"])
        self.assertEqual(result["noteBucketLabel"], "Planning")
        self.assertEqual(result["mergedBucketCount"], 1)
        self.assertEqual(result["mergedBucketLabel"], "Planning")
        self.assertEqual(result["mergedBucketNotes"], 3)

    def test_canvas_notes_separates_overlapping_bucket_areas(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_SEPARATION_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.importJSON(JSON.stringify({
        kind:'kyanbasu.notes',
        version:1,
        notes:[
          {id:'plan-note', x:220, y:240, content:'Plan', bucket:'Planning'},
          {id:'ship-note', x:250, y:265, content:'Ship', bucket:'Delivery'}
        ],
        links:[],
        buckets:{
          Planning:{dx:0, dy:0, followNotes:true},
          Delivery:{dx:0, dy:0, followNotes:true}
        }
      }));
      setTimeout(function(){
        var a = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
        var b = document.querySelector('.tcNoteBucket[data-bucket="Delivery"]');
        var deliveryNote = document.querySelector('.tcNoteNode[data-note-id="ship-note"]');
        var ar = a.getBoundingClientRect();
        var br = b.getBoundingClientRect();
        var nr = deliveryNote.getBoundingClientRect();
        var overlap = !(ar.right <= br.left || ar.left >= br.right || ar.bottom <= br.top || ar.top >= br.bottom);
        var noteInsideBucket = nr.left >= br.left && nr.top >= br.top && nr.right <= br.right && nr.bottom <= br.bottom;
        var out = {
          bucketCount: document.querySelectorAll('.tcNoteBucket').length,
          overlap: overlap,
          noteInsideBucket: noteInsideBucket
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["bucketCount"], 2)
        self.assertFalse(result["overlap"], msg=json.dumps(result))
        self.assertTrue(result["noteInsideBucket"], msg=json.dumps(result))

    def test_canvas_notes_repel_away_from_bucket_boxes_when_created(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_REPEL_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var anchor = window.KyanbasuNotes.createNote(180, 220, "Anchor", "", "Planning");
      var mover = window.KyanbasuNotes.createNote(410, 220, "Mover", "", "Delivery");
      setTimeout(function(){
        var bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
        var note = document.querySelector('.tcNoteNode[data-note-id="'+mover.id+'"]');
        var bucketRect = bucket.getBoundingClientRect();
        var noteRect = note.getBoundingClientRect();
        var overlap = function(a, b){
          return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
        };
        var out = {
          movedClear: !overlap(bucketRect, noteRect),
          movedSideways: Math.abs(parseFloat(note.style.top || '0') - 220) <= 6 && Math.abs(parseFloat(note.style.left || '0') - 410) > 5,
          bucketLabel: bucket.getAttribute('data-bucket') || ''
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 220);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["movedClear"], msg=json.dumps(result))
        self.assertTrue(result["movedSideways"], msg=json.dumps(result))
        self.assertEqual(result["bucketLabel"], "Planning")

    def test_canvas_notes_dragging_note_into_bucket_reassigns_it(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_DRAG_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var target = window.KyanbasuNotes.createNote(520, 260, "Bucket note", "", "Planning");
      var moving = window.KyanbasuNotes.createNote(120, 260, "Move me", "", "(no bucket)");
      var movingEl = document.querySelector('.tcNoteNode[data-note-id="'+moving.id+'"]');
      var head = movingEl.querySelector('.tcNoteHead');
      var targetEl = document.querySelector('.tcNoteNode[data-note-id="'+target.id+'"]');
      var t = targetEl.getBoundingClientRect();
      var h = head.getBoundingClientRect();
      function fire(node, type, x, y, extra){
        node.dispatchEvent(new MouseEvent(type, Object.assign({
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:x,
          clientY:y
        }, extra || {})));
      }
      fire(head, 'mousedown', h.left + 8, h.top + 8);
      fire(document, 'mousemove', t.left + t.width / 2, t.top + t.height / 2);
      fire(document, 'mouseup', t.left + t.width / 2, t.top + t.height / 2);
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var moved = notes.filter(function(n){ return n.content === 'Move me'; })[0];
        var out = {
          movedBucket: moved && moved.bucket,
          bucketCount: document.querySelectorAll('.tcNoteBucket').length,
          bucketLabel: (document.querySelector('.tcNoteBucketTitle') || {}).textContent || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["movedBucket"], "Planning")
        self.assertGreaterEqual(result["bucketCount"], 1)
        self.assertEqual(result["bucketLabel"], "Planning")

    def test_canvas_notes_renames_bucket_from_header(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_RENAME_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "Alpha", "", "Planning");
      var b = window.KyanbasuNotes.createNote(460, 240, "Beta", "", "Planning");
      var bucketBtn = document.querySelector('.tcNoteBucketTitle');
      window.prompt = function(){ return 'Roadmap'; };
      bucketBtn.click();
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var out = {
          renamedCount: notes.filter(function(n){ return n.bucket === 'Roadmap'; }).length,
          bucketLabel: (document.querySelector('.tcNoteBucketTitle') || {}).textContent || "",
          noteHeader: document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"] .tcNoteBucketLabel').textContent
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["renamedCount"], 2)
        self.assertEqual(result["bucketLabel"], "Roadmap")
        self.assertEqual(result["noteHeader"], "Roadmap")

    def test_canvas_notes_collapses_and_expands_bucket(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_COLLAPSE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.createNote(180, 220, "One", "", "Planning");
      window.KyanbasuNotes.createNote(480, 260, "Two", "", "Planning");
      window.KyanbasuNotes.createNote(820, 240, "Three", "", "Delivery");
      var toggle = document.querySelector('.tcNoteBucket[data-bucket="Planning"] .tcNoteBucketToggle');
      toggle.click();
      setTimeout(function(){
        var collapsedVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){
          return el.style.display !== 'none';
        }).length;
        var collapsedClass = document.querySelector('.tcNoteBucket[data-bucket="Planning"]').classList.contains('collapsed');
        toggle = document.querySelector('.tcNoteBucket[data-bucket="Planning"] .tcNoteBucketToggle');
        toggle.click();
        setTimeout(function(){
          var expandedVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){
            return el.style.display !== 'none';
          }).length;
          var out = {
            collapsedVisible: collapsedVisible,
            collapsedClass: collapsedClass,
            expandedVisible: expandedVisible,
            bucketCount: document.querySelectorAll('.tcNoteBucket').length
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 160);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["collapsedVisible"], 1)
        self.assertTrue(result["collapsedClass"])
        self.assertEqual(result["expandedVisible"], 3)
        self.assertEqual(result["bucketCount"], 2)

    def test_canvas_notes_drag_bucket_moves_all_notes_in_bucket(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_MOVE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 220, "One", "", "Planning");
      var b = window.KyanbasuNotes.createNote(480, 260, "Two", "", "Planning");
      var c = window.KyanbasuNotes.createNote(820, 240, "Three", "", "Delivery");
      var bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
      var head = bucket.querySelector('.tcNoteBucketHead');
      var before = {
        left: parseFloat(bucket.style.left || '0'),
        top: parseFloat(bucket.style.top || '0'),
        aLeft: parseFloat(document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]').style.left || '0'),
        aTop: parseFloat(document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]').style.top || '0'),
        bLeft: parseFloat(document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]').style.left || '0'),
        bTop: parseFloat(document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]').style.top || '0'),
        cLeft: parseFloat(document.querySelector('.tcNoteNode[data-note-id="'+c.id+'"]').style.left || '0'),
        cTop: parseFloat(document.querySelector('.tcNoteNode[data-note-id="'+c.id+'"]').style.top || '0')
      };
      var r = head.getBoundingClientRect();
      function fire(node, type, x, y){
        node.dispatchEvent(new MouseEvent(type, {
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:x,
          clientY:y
        }));
      }
      fire(head, 'mousedown', r.left + 8, r.top + 8);
      fire(document, 'mousemove', r.left + 168, r.top + 108);
      fire(document, 'mouseup', r.left + 168, r.top + 108);
      setTimeout(function(){
        var bucketAfter = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
        var notes = window.KyanbasuNotes.notes();
        var notesByContent = {};
        notes.forEach(function(n){ notesByContent[n.content] = n; });
        var out = {
          bucketMoved: parseFloat(bucketAfter.style.left || '0') - before.left,
          bucketMovedY: parseFloat(bucketAfter.style.top || '0') - before.top,
          aMoved: Math.abs(notesByContent.One.x - before.aLeft) > 70 || Math.abs(notesByContent.One.y - before.aTop) > 40,
          bMoved: Math.abs(notesByContent.Two.x - before.bLeft) > 70 || Math.abs(notesByContent.Two.y - before.bTop) > 40,
          cYielded: Math.abs(notesByContent.Three.x - before.cLeft) > 20 || Math.abs(notesByContent.Three.y - before.cTop) > 20,
          bucketLabel: (document.querySelector('.tcNoteBucket[data-bucket="Planning"] .tcNoteBucketTitle') || {}).textContent || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertGreater(result["bucketMoved"], 80)
        self.assertGreater(result["bucketMovedY"], 40)
        self.assertTrue(result["aMoved"])
        self.assertTrue(result["bMoved"])
        self.assertTrue(result["cYielded"])
        self.assertEqual(result["bucketLabel"], "Planning")

    def test_canvas_notes_dragged_bucket_holds_drop_position_and_displaces_neighbors(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_PRIORITY_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.createNote(180, 240, "Left", "", "Left bucket");
      window.KyanbasuNotes.createNote(650, 240, "Right", "", "Right bucket");
      var draggedNote = window.KyanbasuNotes.createNote(1220, 240, "Dragged", "", "Dragged bucket");
      var leftBefore = document.querySelector('.tcNoteBucket[data-bucket="Left bucket"]').getBoundingClientRect();
      var rightBefore = document.querySelector('.tcNoteBucket[data-bucket="Right bucket"]').getBoundingClientRect();
      var dragged = document.querySelector('.tcNoteBucket[data-bucket="Dragged bucket"]');
      var draggedBefore = dragged.getBoundingClientRect();
      var noteBefore = document.querySelector('.tcNoteNode[data-note-id="'+draggedNote.id+'"]').getBoundingClientRect();
      var head = dragged.querySelector('.tcNoteBucketHead');
      var headRect = head.getBoundingClientRect();
      var targetLeft = (leftBefore.right + rightBefore.left - draggedBefore.width) / 2;
      var deltaX = targetLeft - draggedBefore.left;
      function fire(node, type, x, y){
        node.dispatchEvent(new MouseEvent(type, {
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:x,
          clientY:y
        }));
      }
      fire(head, 'mousedown', headRect.left + 12, headRect.top + 10);
      fire(document, 'mousemove', headRect.left + 12 + deltaX, headRect.top + 10);
      fire(document, 'mouseup', headRect.left + 12 + deltaX, headRect.top + 10);
      setTimeout(function(){
        var leftAfter = document.querySelector('.tcNoteBucket[data-bucket="Left bucket"]').getBoundingClientRect();
        var rightAfter = document.querySelector('.tcNoteBucket[data-bucket="Right bucket"]').getBoundingClientRect();
        var draggedAfter = document.querySelector('.tcNoteBucket[data-bucket="Dragged bucket"]').getBoundingClientRect();
        var noteAfter = document.querySelector('.tcNoteNode[data-note-id="'+draggedNote.id+'"]').getBoundingClientRect();
        function overlaps(a, b){
          return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        }
        var out = {
          heldDropPosition: Math.abs(draggedAfter.left - targetLeft) < 5,
          leftDisplaced: Math.abs(leftAfter.left - leftBefore.left) > 20,
          rightDisplaced: Math.abs(rightAfter.left - rightBefore.left) > 20,
          notesStayedAttached: Math.abs((noteAfter.left - draggedAfter.left) - (noteBefore.left - draggedBefore.left)) < 5,
          bucketsSeparated: !overlaps(draggedAfter, leftAfter) && !overlaps(draggedAfter, rightAfter),
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["heldDropPosition"], msg=json.dumps(result))
        self.assertTrue(result["leftDisplaced"], msg=json.dumps(result))
        self.assertTrue(result["rightDisplaced"], msg=json.dumps(result))
        self.assertTrue(result["notesStayedAttached"], msg=json.dumps(result))
        self.assertTrue(result["bucketsSeparated"], msg=json.dumps(result))
        self.assertEqual(result["console"], "")

    def test_canvas_notes_moves_bucket_without_moving_notes_and_round_trips_layout(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_LAYOUT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 220, "One", "", "Planning");
      var b = window.KyanbasuNotes.createNote(480, 260, "Two", "", "Planning");
      var c = window.KyanbasuNotes.createNote(820, 240, "Three", "", "Delivery");
      var bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
      var head = bucket.querySelector('.tcNoteBucketHead');
      var aEl = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
      var bEl = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
      var cEl = document.querySelector('.tcNoteNode[data-note-id="'+c.id+'"]');
      bucket.querySelector('.tcNoteBucketFollow').click();
      bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
      head = bucket.querySelector('.tcNoteBucketHead');
      var before = {
        bucketLeft: parseFloat(bucket.style.left || '0'),
        bucketTop: parseFloat(bucket.style.top || '0'),
        aLeft: parseFloat(aEl.style.left || '0'),
        aTop: parseFloat(aEl.style.top || '0'),
        bLeft: parseFloat(bEl.style.left || '0'),
        bTop: parseFloat(bEl.style.top || '0'),
        cLeft: parseFloat(cEl.style.left || '0'),
        cTop: parseFloat(cEl.style.top || '0')
      };
      function fire(node, type, x, y){
        node.dispatchEvent(new MouseEvent(type, {
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:x,
          clientY:y
        }));
      }
      var r = head.getBoundingClientRect();
      fire(head, 'mousedown', r.left + 10, r.top + 10);
      fire(document, 'mousemove', r.left + 190, r.top + 120);
      fire(document, 'mouseup', r.left + 190, r.top + 120);
      setTimeout(function(){
        var exported = window.KyanbasuNotes.exportData();
        window.KyanbasuNotes.importJSON(JSON.stringify(exported));
        setTimeout(function(){
        var bucketAfter = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
        var aAfter = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
        var bAfter = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
        var cAfter = document.querySelector('.tcNoteNode[data-note-id="'+c.id+'"]');
        var out = {
          bucketMoved: (parseFloat(bucketAfter.style.left || '0') - before.bucketLeft) > 80,
          bucketMovedY: (parseFloat(bucketAfter.style.top || '0') - before.bucketTop) > 40,
          notesStayed: Math.abs(parseFloat(aAfter.style.left || '0') - before.aLeft) < 5 &&
              Math.abs(parseFloat(aAfter.style.top || '0') - before.aTop) < 5 &&
              Math.abs(parseFloat(bAfter.style.left || '0') - before.bLeft) < 5 &&
              Math.abs(parseFloat(bAfter.style.top || '0') - before.bTop) < 5 &&
              Math.abs(parseFloat(cAfter.style.left || '0') - before.cLeft) < 5 &&
              Math.abs(parseFloat(cAfter.style.top || '0') - before.cTop) < 5,
          exportedDx: exported.buckets && exported.buckets.Planning && exported.buckets.Planning.dx,
          exportedDy: exported.buckets && exported.buckets.Planning && exported.buckets.Planning.dy,
          reloadedLeft: parseFloat(bucketAfter.style.left || '0'),
          reloadedTop: parseFloat(bucketAfter.style.top || '0')
        };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["bucketMoved"])
        self.assertTrue(result["bucketMovedY"])
        self.assertTrue(result["notesStayed"])
        self.assertNotEqual(result["exportedDx"], 0)
        self.assertNotEqual(result["exportedDy"], 0)
        self.assertGreater(result["reloadedLeft"], 0)
        self.assertGreater(result["reloadedTop"], 0)

    def test_canvas_notes_follow_toggle_moves_notes_with_bucket_and_persists(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_FOLLOW_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 220, "One", "", "Planning");
      var b = window.KyanbasuNotes.createNote(480, 260, "Two", "", "Planning");
      var bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
      var followBtn = bucket.querySelector('.tcNoteBucketFollow');
      var head = bucket.querySelector('.tcNoteBucketHead');
      var beforeA = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
      var beforeB = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
      var base = {
        aLeft: parseFloat(beforeA.style.left || '0'),
        aTop: parseFloat(beforeA.style.top || '0'),
        bLeft: parseFloat(beforeB.style.left || '0'),
        bTop: parseFloat(beforeB.style.top || '0')
      };
      bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
      followBtn = bucket.querySelector('.tcNoteBucketFollow');
      head = bucket.querySelector('.tcNoteBucketHead');
      var r = head.getBoundingClientRect();
      function fire(node, type, x, y){
        node.dispatchEvent(new MouseEvent(type, {
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:x,
          clientY:y
        }));
      }
      fire(head, 'mousedown', r.left + 12, r.top + 12);
      fire(document, 'mousemove', r.left + 152, r.top + 92);
      fire(document, 'mouseup', r.left + 152, r.top + 92);
      setTimeout(function(){
        var exported = window.KyanbasuNotes.exportData();
        window.KyanbasuNotes.importJSON(JSON.stringify(exported));
        setTimeout(function(){
          var aAfter = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
          var bAfter = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
          var bucketAfter = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
          var followAfter = bucketAfter.querySelector('.tcNoteBucketFollow');
          var out = {
            movedA: Math.abs(parseFloat(aAfter.style.left || '0') - base.aLeft) > 70 || Math.abs(parseFloat(aAfter.style.top || '0') - base.aTop) > 40,
            movedB: Math.abs(parseFloat(bAfter.style.left || '0') - base.bLeft) > 70 || Math.abs(parseFloat(bAfter.style.top || '0') - base.bTop) > 40,
            exportedFollow: exported.buckets && exported.buckets.Planning && exported.buckets.Planning.followNotes,
            reloadedFollow: followAfter && followAfter.getAttribute('aria-pressed') === 'true',
            defaultFollow: followBtn && followBtn.getAttribute('aria-pressed') === 'true'
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["movedA"])
        self.assertTrue(result["movedB"])
        self.assertTrue(result["exportedFollow"])
        self.assertTrue(result["reloadedFollow"])
        self.assertTrue(result["defaultFollow"])

    def test_canvas_notes_colours_bucket_and_notes_and_persists_them(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BUCKET_COLOR_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(200, 220, "Alpha", "", "Planning");
      window.KyanbasuNotes.createNote(520, 260, "Beta", "", "Delivery");
      var bucket = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
      var note = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
      var colorBtn = bucket.querySelector('.tcNoteBucketColor');
      var initialBucket = bucket.style.getPropertyValue('--bucket-accent').trim();
      var initialNote = note.style.getPropertyValue('--note-accent').trim();
      colorBtn.click();
      setTimeout(function(){
        var bucketAfter = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
        var noteAfter = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
        var exported = window.KyanbasuNotes.exportData();
        window.KyanbasuNotes.importJSON(JSON.stringify(exported));
        setTimeout(function(){
          var bucketReloaded = document.querySelector('.tcNoteBucket[data-bucket="Planning"]');
          var noteReloaded = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
          var out = {
            initialBucket: initialBucket,
            initialNote: initialNote,
            afterBucket: bucketAfter.style.getPropertyValue('--bucket-accent').trim(),
            afterNote: noteAfter.style.getPropertyValue('--note-accent').trim(),
            exportedColor: exported.buckets && exported.buckets.Planning && exported.buckets.Planning.color,
            reloadedBucket: bucketReloaded.style.getPropertyValue('--bucket-accent').trim(),
            reloadedNote: noteReloaded.style.getPropertyValue('--note-accent').trim()
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["initialBucket"], result["initialNote"])
        self.assertEqual(result["afterBucket"], result["afterNote"])
        self.assertEqual(result["reloadedBucket"], result["reloadedNote"])
        self.assertNotEqual(result["initialBucket"], result["afterBucket"])
        self.assertEqual(result["afterBucket"], result["exportedColor"])
        self.assertEqual(result["reloadedBucket"], result["afterBucket"])

    def test_drawer_tasks_make_notes_move_aside_when_added_to_canvas(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({
            "tasks": [
                {"uuid": "task-1", "short": "task-1", "desc": "Alpha task", "project": "Alpha", "tags": ["Planning"], "has_depends": False}
            ],
            "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}
        })
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_DRAWER_REPEL_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.createNote(-180, 20, "Note block", "", "Planning");
      addToBuilder(TASKS[0], null, null);
        setTimeout(function(){
          var note = document.querySelector('.tcNoteNode');
          var proj = document.querySelector('.projArea[data-proj="Alpha"]');
          var task = document.querySelector('.node[data-short="task-1"]');
          var stage = document.getElementById('builderStage');
          var nr = note.getBoundingClientRect();
          var pr = proj.getBoundingClientRect();
          var sr = stage.getBoundingClientRect();
          var tr = task.getBoundingClientRect();
          var overlap = function(a, b){
            return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
          };
          var out = {
            projectStayedAtOrigin: Math.abs(parseFloat(proj.style.left || '0') - 20) <= 1 && Math.abs(parseFloat(proj.style.top || '0') - 20) <= 1,
            noteMovedAside: parseFloat(note.style.left || '0') >= 0 && (nr.right <= pr.left - 5 || nr.left >= pr.right + 5 || nr.bottom <= pr.top - 5 || nr.top >= pr.bottom + 5),
            projectInBounds: pr.left >= sr.left - 1 && pr.top >= sr.top - 1 && pr.right <= sr.right + 1 && pr.bottom <= sr.bottom + 1,
            projectClear: !overlap(nr, pr),
            taskClear: !overlap(nr, tr)
          };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 220);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["projectStayedAtOrigin"], msg=json.dumps(result))
        self.assertTrue(result["noteMovedAside"], msg=json.dumps(result))
        self.assertTrue(result["projectInBounds"], msg=json.dumps(result))
        self.assertTrue(result["projectClear"], msg=json.dumps(result))
        self.assertTrue(result["taskClear"], msg=json.dumps(result))

    def test_project_drag_into_note_area_pushes_notes_not_project(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({
            "tasks": [
                {"uuid": "task-1", "short": "task-1", "desc": "Alpha task", "project": "Alpha", "tags": ["Planning"], "has_depends": False}
            ],
            "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}
        })
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_PROJECT_DRAG_PUSHES_NOTES_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.createNote(520, 300, "Note block", "", "Planning");
      addToBuilder(TASKS[0], null, null);
      setTimeout(function(){
        moveWholeProject("Alpha", 500, 280);
        settleCanvasAgainstNotes();
        setTimeout(function(){
          var note = document.querySelector('.tcNoteNode');
          var proj = document.querySelector('.projArea[data-proj="Alpha"]');
          var nr = note.getBoundingClientRect();
          var pr = proj.getBoundingClientRect();
          var overlap = function(a, b){
            return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
          };
          var out = {
            projectX: parseFloat(proj.style.left || '0'),
            projectY: parseFloat(proj.style.top || '0'),
            noteX: parseFloat(note.style.left || '0'),
            noteY: parseFloat(note.style.top || '0'),
            projectKeptDrop: Math.abs(parseFloat(proj.style.left || '0') - 520) <= 1 && Math.abs(parseFloat(proj.style.top || '0') - 300) <= 1,
            noteMoved: Math.abs(parseFloat(note.style.left || '0') - 520) > 5 || Math.abs(parseFloat(note.style.top || '0') - 300) > 5,
            clear: !overlap(nr, pr)
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 160);
      }, 220);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["projectKeptDrop"], msg=json.dumps(result))
        self.assertTrue(result["noteMoved"], msg=json.dumps(result))
        self.assertTrue(result["clear"], msg=json.dumps(result))

    def test_note_placement_in_project_area_pushes_project_aside(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({
            "tasks": [
                {"uuid": "task-1", "short": "task-1", "desc": "Alpha task", "project": "Alpha", "tags": ["Planning"], "has_depends": False}
            ],
            "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}
        })
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_NOTE_PLACEMENT_PUSHES_PROJECT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      addToBuilder(TASKS[0], null, null);
      setTimeout(function(){
        window.KyanbasuNotes.createNote(36, 36, "Note block", "", "Planning");
        setTimeout(function(){
          var note = document.querySelector('.tcNoteNode');
          var bucket = document.querySelector('.tcNoteBucket');
          var proj = document.querySelector('.projArea[data-proj="Alpha"]');
          var nr = note.getBoundingClientRect();
          var br = bucket.getBoundingClientRect();
          var pr = proj.getBoundingClientRect();
          var overlap = function(a, b){
            return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
          };
          var out = {
            noteKeptPlacement: Math.abs(parseFloat(note.style.left || '0') - 36) <= 1 && Math.abs(parseFloat(note.style.top || '0') - 36) <= 1,
            projectMoved: Math.abs(parseFloat(proj.style.left || '0') - 20) > 5 || Math.abs(parseFloat(proj.style.top || '0') - 20) > 5,
            projectClearOfNote: !overlap(nr, pr),
            projectClearOfBucket: !overlap(br, pr)
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["noteKeptPlacement"], msg=json.dumps(result))
        self.assertTrue(result["projectMoved"], msg=json.dumps(result))
        self.assertTrue(result["projectClearOfNote"], msg=json.dumps(result))
        self.assertTrue(result["projectClearOfBucket"], msg=json.dumps(result))

    def test_note_bucket_move_into_project_area_pushes_project_aside(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({
            "tasks": [
                {"uuid": "task-1", "short": "task-1", "desc": "Alpha task", "project": "Alpha", "tags": ["Planning"], "has_depends": False}
            ],
            "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}
        })
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_NOTE_BUCKET_PUSHES_PROJECT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      addToBuilder(TASKS[0], null, null);
      setTimeout(function(){
        var note = window.KyanbasuNotes.createNote(720, 420, "Note block", "", "Planning", {skipAutoLayout:true});
        note.x = 36;
        note.y = 36;
        window.KyanbasuNotes.render();
        settleProjectsAgainstNotes();
        setTimeout(function(){
          var bucket = document.querySelector('.tcNoteBucket');
          var proj = document.querySelector('.projArea[data-proj="Alpha"]');
          var br = bucket.getBoundingClientRect();
          var pr = proj.getBoundingClientRect();
          var overlap = function(a, b){
            return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
          };
          var out = {
            bucketAtDrop: parseFloat(bucket.style.left || '0') < 60 && parseFloat(bucket.style.top || '0') < 60,
            projectMoved: Math.abs(parseFloat(proj.style.left || '0') - 20) > 5 || Math.abs(parseFloat(proj.style.top || '0') - 20) > 5,
            clear: !overlap(br, pr)
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 180);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["bucketAtDrop"], msg=json.dumps(result))
        self.assertTrue(result["projectMoved"], msg=json.dumps(result))
        self.assertTrue(result["clear"], msg=json.dumps(result))

    def test_canvas_notes_focuses_branch_and_bucket_across_builder_and_viewer(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTE_FOCUS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 220, 'Root idea', '', 'Planning', {skipAutoLayout:true});
      var child = window.KyanbasuNotes.createChildNote(root.id, 'Child idea', '');
      window.KyanbasuNotes.createChildNote(child.id, 'Nested idea', '');
      window.KyanbasuNotes.createNote(820, 220, 'Other planning root', '', 'Planning', {skipAutoLayout:true});
      window.KyanbasuNotes.createNote(820, 480, 'Delivery root', '', 'Delivery', {skipAutoLayout:true});
      window.KyanbasuNotes.toggleCollapse(root.id);
      window.KyanbasuNotes.focusBranch(root.id);
      var branchVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length;
      var branchState = window.KyanbasuNotes.focusState();
      var branchOutline = window.KyanbasuNotes.visibleOutline();
      var focusBar = (document.getElementById('tcNoteFocusBar') || {}).textContent || '';
      document.getElementById('tabViewer').click();
      setTimeout(function(){
        var viewerTitle = (document.querySelectorAll('#viewerStage .viewerSectionTitle')[1] || {}).textContent || '';
        var viewerRows = document.querySelectorAll('#viewerStage .viewerNote').length;
        var showAll = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerSortBtn')).filter(function(btn){ return btn.textContent === 'Show all'; })[0];
        showAll.click();
        setTimeout(function(){
          var allRows = document.querySelectorAll('#viewerStage .viewerNote').length;
          document.getElementById('tabBuilder').click();
          window.KyanbasuNotes.focusBucket('Planning');
          var bucketVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length;
          var bucketBoxes = document.querySelectorAll('#tcNoteBucketsLayer .tcNoteBucket').length;
          var bucketState = window.KyanbasuNotes.focusState();
          document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
          setTimeout(function(){
            var out = {
              branchVisible:branchVisible,
              branchState:branchState,
              branchRoots:branchOutline.map(function(item){ return item.id; }),
              focusBar:focusBar,
              viewerTitle:viewerTitle,
              viewerRows:viewerRows,
              allRows:allRows,
              bucketVisible:bucketVisible,
              bucketBoxes:bucketBoxes,
              bucketState:bucketState,
              afterEscape:window.KyanbasuNotes.focusState().kind,
              allVisible:Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 100);
        }, 100);
      }, 140);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["branchVisible"], 3, msg=json.dumps(result))
        self.assertEqual(result["branchState"]["kind"], "branch", msg=json.dumps(result))
        self.assertEqual(result["branchState"]["count"], 3, msg=json.dumps(result))
        self.assertEqual(len(result["branchRoots"]), 1, msg=json.dumps(result))
        self.assertIn("Branch A1", result["focusBar"], msg=json.dumps(result))
        self.assertIn("Notes · Branch A1", result["viewerTitle"], msg=json.dumps(result))
        self.assertEqual(result["viewerRows"], 3, msg=json.dumps(result))
        self.assertEqual(result["allRows"], 5, msg=json.dumps(result))
        self.assertEqual(result["bucketVisible"], 4, msg=json.dumps(result))
        self.assertEqual(result["bucketBoxes"], 1, msg=json.dumps(result))
        self.assertEqual(result["bucketState"]["kind"], "bucket", msg=json.dumps(result))
        self.assertEqual(result["afterEscape"], "none", msg=json.dumps(result))
        self.assertEqual(result["allVisible"], 5, msg=json.dumps(result))

    def test_viewer_note_outliner_edits_and_creates_siblings_and_children(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_EDITABLE_NOTE_OUTLINER_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, 'Initial thought', '', 'Planning');
      document.getElementById('tabViewer').click();
      setTimeout(function(){
        var rootRow = document.querySelector('#viewerStage .viewerNote[data-note-id="'+root.id+'"]');
        var editor = rootRow.querySelector('.viewerNoteText');
        editor.focus();
        editor.textContent = 'Edited thought';
        editor.dispatchEvent(new Event('input', {bubbles:true}));
        editor.dispatchEvent(new KeyboardEvent('keydown', {key:'Tab', bubbles:true, cancelable:true}));
        setTimeout(function(){
          var selectedId = window.KyanbasuNotes.primaryNote();
          var childEditor = document.querySelector('#viewerStage .viewerNote[data-note-id="'+selectedId+'"] .viewerNoteText');
          childEditor.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
          setTimeout(function(){
            var outline = window.KyanbasuNotes.outline();
            var rootAfter = outline.filter(function(item){ return item.id === root.id; })[0];
            var selectedRowsBefore = document.querySelectorAll('#viewerStage .viewerNote.selected').length;
            var inspectorKindBefore = !!document.getElementById('inspectorNoteKind');
            var toggle = document.querySelector('#viewerStage .viewerNote[data-note-id="'+root.id+'"] .viewerNoteToggle');
            toggle.click();
            setTimeout(function(){
              var collapsedRows = document.querySelectorAll('#viewerStage .viewerNote').length;
              var out = {
                content:window.KyanbasuNotes.notes().filter(function(note){ return note.id === root.id; })[0].content,
                notes:window.KyanbasuNotes.notes().length,
                childCount:rootAfter && rootAfter.children.length,
                childDepths:(rootAfter && rootAfter.children || []).map(function(item){ return item.depth; }),
                collapsedRows:collapsedRows,
                selectedRows:selectedRowsBefore,
                contentEditable:editor.getAttribute('contenteditable'),
                inspectorKind:inspectorKindBefore
              };
              var pre = document.createElement('pre');
              pre.id = 'e2e-out';
              pre.textContent = JSON.stringify(out);
              document.body.appendChild(pre);
            }, 100);
          }, 120);
        }, 120);
      }, 140);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["content"], "Edited thought", msg=json.dumps(result))
        self.assertEqual(result["notes"], 3, msg=json.dumps(result))
        self.assertEqual(result["childCount"], 2, msg=json.dumps(result))
        self.assertEqual(result["childDepths"], [1, 1], msg=json.dumps(result))
        self.assertEqual(result["collapsedRows"], 1, msg=json.dumps(result))
        self.assertEqual(result["selectedRows"], 1, msg=json.dumps(result))
        self.assertEqual(result["contentEditable"], "true", msg=json.dumps(result))
        self.assertTrue(result["inspectorKind"], msg=json.dumps(result))

    def test_viewer_renders_task_section_and_note_outline(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({
            "tasks": [
                {"uuid": "task-1", "short": "A", "desc": "Parent task", "project": "Work", "tags": ["Plan"], "has_depends": False},
                {"uuid": "task-2", "short": "B", "desc": "Dependent task", "project": "Work", "tags": ["Build"], "has_depends": True},
                {"uuid": "task-3", "short": "C", "desc": "Dependent task two", "project": "Ops", "tags": ["Run"], "has_depends": True}
            ],
            "graph": {"edges": [{"from": "A", "to": "B"}, {"from": "A", "to": "C"}], "parent_current_deps": {"B": ["A"], "C": ["A"]}, "child_to_parents": {"B": ["A"], "C": ["A"]}}
        })
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_VIEWER_NOTES_OUTLINE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Launch plan", "", "Planning");
      var child = window.KyanbasuNotes.createChildNote(root.id, "Build prototype", "");
      window.KyanbasuNotes.setBucket(child.id, "Delivery");
      document.getElementById('tabViewer').click();
      setTimeout(function(){
        var sections = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerSectionTitle')).map(function(el){ return el.textContent; });
        var taskItems = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerItem .desc')).map(function(el){ return el.textContent; });
        var taskSection = document.querySelectorAll('#viewerStage .viewerSection')[0];
        var notesSection = document.querySelectorAll('#viewerStage .viewerSection')[1];
        var tr = taskSection.getBoundingClientRect();
        var nrSection = notesSection.getBoundingClientRect();
        var notesHead = notesSection.querySelector('.viewerSectionHead').getBoundingClientRect();
        var sortControls = notesSection.querySelector('.viewerSectionActions').getBoundingClientRect();
        var noteRows = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerNote')).map(function(el){
          return {
            code: (el.querySelector('.viewerNoteCode') || {}).textContent || "",
            text: (el.querySelector('.viewerNoteText') || {}).textContent || "",
            bucket: (el.querySelector('.viewerNoteBucket') || {}).textContent || "",
            indent: parseFloat(el.style.marginLeft || '0')
          };
        });
        var out = {
          sections: sections,
          taskItems: taskItems,
          noteRows: noteRows,
          sortButtons: Array.prototype.slice.call(document.querySelectorAll('#viewerStage [data-viewer-note-sort]')).map(function(el){ return el.textContent; }),
          sectionsSeparated: nrSection.top > tr.bottom + 20,
          sortControlsBelowHeader: sortControls.top > notesHead.bottom - 1,
          sortControlsVisible: sortControls.width > 80 && sortControls.height > 20,
          taskEmpty: !!Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerEmpty')).filter(function(el){ return el.textContent === 'No dependent tasks.'; }).length,
          notesEmpty: !!Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerEmpty')).filter(function(el){ return el.textContent === 'No planning notes.'; }).length
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["sections"], ["Tasks", "Notes"], msg=json.dumps(result))
        self.assertIn("Dependent task", result["taskItems"], msg=json.dumps(result))
        self.assertIn("Dependent task two", result["taskItems"], msg=json.dumps(result))
        self.assertEqual(result["sortButtons"], ["ID", "Bucket"], msg=json.dumps(result))
        self.assertTrue(result["sectionsSeparated"], msg=json.dumps(result))
        self.assertTrue(result["sortControlsBelowHeader"], msg=json.dumps(result))
        self.assertTrue(result["sortControlsVisible"], msg=json.dumps(result))
        self.assertFalse(result["taskEmpty"], msg=json.dumps(result))
        self.assertFalse(result["notesEmpty"], msg=json.dumps(result))
        self.assertEqual([row["text"] for row in result["noteRows"]], ["Launch plan", "Build prototype"], msg=json.dumps(result))
        self.assertEqual(result["noteRows"][0]["code"], "A1", msg=json.dumps(result))
        self.assertEqual(result["noteRows"][1]["code"], "A1-1", msg=json.dumps(result))
        self.assertEqual(result["noteRows"][0]["bucket"], "Planning", msg=json.dumps(result))
        self.assertEqual(result["noteRows"][1]["bucket"], "Delivery", msg=json.dumps(result))
        self.assertGreater(result["noteRows"][1]["indent"], result["noteRows"][0]["indent"], msg=json.dumps(result))

    def test_viewer_note_outline_sorts_roots_by_bucket(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_VIEWER_NOTES_SORT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      localStorage.removeItem('kyanbasu:viewer:notes-sort');
      localStorage.removeItem('kyanbasu:viewer:notes-sort');
      var z = window.KyanbasuNotes.createNote(120, 220, "Zeta root", "", "Zeta", {skipAutoLayout:true});
      window.KyanbasuNotes.createChildNote(z.id, "Zeta child", "");
      window.KyanbasuNotes.createNote(420, 220, "Alpha root", "", "Alpha", {skipAutoLayout:true});
      document.getElementById('tabViewer').click();
      setTimeout(function(){
        var before = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerNoteText')).map(function(el){ return el.textContent; });
        document.querySelector('#viewerStage [data-viewer-note-sort="bucket"]').click();
        setTimeout(function(){
          var after = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerNoteText')).map(function(el){ return el.textContent; });
          var active = (document.querySelector('#viewerStage .viewerSortBtn.active') || {}).textContent || "";
          var stored = localStorage.getItem('kyanbasu:viewer:notes-sort') || "";
          var indents = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerNote')).map(function(el){ return parseFloat(el.style.marginLeft || '0'); });
          var out = {before:before, after:after, active:active, stored:stored, indents:indents};
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 120);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["before"], ["Zeta root", "Zeta child", "Alpha root"], msg=json.dumps(result))
        self.assertEqual(result["after"], ["Alpha root", "Zeta root", "Zeta child"], msg=json.dumps(result))
        self.assertEqual(result["active"], "Bucket", msg=json.dumps(result))
        self.assertEqual(result["stored"], "bucket", msg=json.dumps(result))
        self.assertGreater(result["indents"][2], result["indents"][1], msg=json.dumps(result))

    def test_project_nearest_open_slot_prefers_close_diagonal_position(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_PROJECT_SLOT_HARNESS">
window.addEventListener('load', function(){
  try{
    var rect = {x:100, y:100, w:100, h:100};
    var obstacles = [
      {x:180, y:100, w:60, h:60},
      {x:100, y:180, w:60, h:60},
      {x:248, y:100, w:60, h:60},
      {x:100, y:248, w:60, h:60}
    ];
    var move = findNearestProjectMove(rect, obstacles);
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = JSON.stringify({
      dx: move && move.dx,
      dy: move && move.dy
    });
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["dx"], -80)
        self.assertEqual(result["dy"], -80)

    def test_canvas_notes_rejects_overlapping_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_OVERLAP_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(260, 260, "Alpha", "", "Planning");
      var b = window.KyanbasuNotes.createNote(260, 260, "Beta", "", "Planning");
      setTimeout(function(){
        var aEl = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
        var bEl = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
        var ar = aEl.getBoundingClientRect();
        var br = bEl.getBoundingClientRect();
        var overlap = !(ar.right <= br.left || ar.left >= br.right || ar.bottom <= br.top || ar.top >= br.bottom);
        var out = {
          overlap: overlap,
          ax: Math.round(ar.left),
          ay: Math.round(ar.top),
          bx: Math.round(br.left),
          by: Math.round(br.top)
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertFalse(result["overlap"])
        self.assertNotEqual(result["ax"], result["bx"])
        self.assertNotEqual(result["ay"], result["by"])

    def test_canvas_notes_create_tasks_stages_selected_note_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_CREATE_TASKS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "Plan branch", "");
      var b = window.KyanbasuNotes.createNote(440, 240, "Build branch", "with details");
      var c = window.KyanbasuNotes.createNote(760, 240, "Ignore branch", "");
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      var count1 = window.KyanbasuNotes.stageSelectedNotesAsTasks();
      var count2 = window.KyanbasuNotes.stageSelectedNotesAsTasks();
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var lines = ((document.getElementById('consoleText') || {}).value || "").split(/\\n/).filter(Boolean);
        var out = {
          button: !!document.getElementById('noteCreateTasksBtn'),
          count1: count1,
          count2: count2,
          staged: Array.isArray(window.STAGED_CMDS) ? window.STAGED_CMDS.slice() : [],
          lines: lines,
          ignorePresent: lines.some(function(line){ return line.indexOf('Ignore branch') !== -1; })
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["button"])
        self.assertEqual(result["count1"], 2)
        self.assertEqual(result["count2"], 2)
        self.assertEqual(len(result["staged"]), 2)
        self.assertEqual(len(result["lines"]), 2)
        self.assertIn("task add 'Plan branch'", result["lines"])
        self.assertIn("task add 'Build branch with details'", result["lines"])
        self.assertFalse(result["ignorePresent"])

    def test_shell_uses_kyanbasu_brand_wordmark(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_KYANBASU_BRAND_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var title = document.querySelector('.shellTitle');
      var kana = document.querySelector('.shellKana');
      var eyebrow = document.querySelector('.shellEyebrow');
      var subtitle = document.querySelector('.shellSubtitle');
      document.getElementById('toggleHeaderTools').click();
      var out = {
        documentTitle:document.title,
        applicationName:(document.querySelector('meta[name="application-name"]') || {}).content || '',
        description:(document.querySelector('meta[name="description"]') || {}).content || '',
        title:title && title.textContent,
        kana:kana && kana.textContent,
        kanaLang:kana && kana.getAttribute('lang'),
        kanaDecorative:kana && kana.getAttribute('aria-hidden'),
        eyebrow:eyebrow && eyebrow.textContent,
        subtitle:subtitle && subtitle.textContent,
        compactWordmarkVisible:getComputedStyle(document.querySelector('.shellWordmark')).display !== 'none'
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["documentTitle"], "Kyanbasu — Visual planning for Taskwarrior", msg=json.dumps(result))
        self.assertEqual(result["applicationName"], "Kyanbasu", msg=json.dumps(result))
        self.assertIn("visual planning workspace", result["description"].lower(), msg=json.dumps(result))
        self.assertEqual(result["title"], "Kyanbasu", msg=json.dumps(result))
        self.assertEqual(result["kana"], "キャンバス", msg=json.dumps(result))
        self.assertEqual(result["kanaLang"], "ja", msg=json.dumps(result))
        self.assertEqual(result["kanaDecorative"], "true", msg=json.dumps(result))
        self.assertEqual(result["eyebrow"], "Visual planning for Taskwarrior", msg=json.dumps(result))
        self.assertIn("Stage dependencies", result["subtitle"], msg=json.dumps(result))
        self.assertTrue(result["compactWordmarkVisible"], msg=json.dumps(result))

    def test_top_toolbar_groups_note_and_command_actions(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_TOP_TOOLBAR_GROUPS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      function parentId(id){
        var el = document.getElementById(id);
        return el && el.parentElement ? el.parentElement.id : "";
      }
      var out = {
        groups: Array.prototype.slice.call(document.querySelectorAll('.shellActions .toolbarGroup')).map(function(el){ return el.id || el.getAttribute('data-label'); }),
        noteParent: parentId('noteModeBtn'),
        linkParent: parentId('noteLinkModeBtn'),
        taskLinkParent: parentId('noteTaskLinkBtn'),
        searchParent: parentId('noteSearchWrap'),
        reflowParent: parentId('noteReflowBtn'),
        linkedParent: parentId('noteCreateLinkedTasksBtn'),
        createParent: parentId('noteCreateTasksBtn'),
        importParent: parentId('noteImportBtn'),
        exportParent: parentId('noteExportBtn'),
        exportAllParent: parentId('noteExportAllBtn'),
        actionStack: !!document.querySelector('.shellActionStack'),
        leftControls: !!document.getElementById('shellLeftControls'),
        workbenchControls: !!document.getElementById('shellWorkbenchControls'),
        modeControls: !!document.querySelector('.shellModeControls'),
        tabbarSibling: document.querySelector('.tabbar') && document.querySelector('.tabbar').parentElement ? document.querySelector('.tabbar').parentElement.className : "",
        workbenchSibling: document.getElementById('shellWorkbenchControls') && document.getElementById('shellWorkbenchControls').parentElement ? document.getElementById('shellWorkbenchControls').parentElement.className : "",
        workbenchParent: parentId('workbenchGroup'),
        canvasParent: document.querySelector('.toolbarGroupCanvas') && document.querySelector('.toolbarGroupCanvas').parentElement ? document.querySelector('.toolbarGroupCanvas').parentElement.id : "",
        secondaryGroups: Array.prototype.slice.call(document.querySelectorAll('.shellActionsSecondary .toolbarGroup')).map(function(el){ return el.id || el.getAttribute('data-label'); }),
        consoleParentClass: document.getElementById('toggleConsole').parentElement.className,
        resetParentClass: document.getElementById('resetCanvas').parentElement.className
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertIn("noteToolsGroup", result["groups"], msg=json.dumps(result))
        self.assertIn("noteTaskGroup", result["groups"], msg=json.dumps(result))
        self.assertIn("noteDataGroup", result["groups"], msg=json.dumps(result))
        self.assertEqual(result["noteParent"], "noteToolsGroup", msg=json.dumps(result))
        self.assertEqual(result["linkParent"], "noteToolsGroup", msg=json.dumps(result))
        self.assertEqual(result["taskLinkParent"], "noteToolsGroup", msg=json.dumps(result))
        self.assertEqual(result["searchParent"], "noteToolsGroup", msg=json.dumps(result))
        self.assertEqual(result["reflowParent"], "noteToolsGroup", msg=json.dumps(result))
        self.assertEqual(result["linkedParent"], "noteTaskGroup", msg=json.dumps(result))
        self.assertEqual(result["createParent"], "noteTaskGroup", msg=json.dumps(result))
        self.assertEqual(result["importParent"], "noteDataGroup", msg=json.dumps(result))
        self.assertEqual(result["exportParent"], "noteDataGroup", msg=json.dumps(result))
        self.assertEqual(result["exportAllParent"], "noteDataGroup", msg=json.dumps(result))
        self.assertTrue(result["actionStack"], msg=json.dumps(result))
        self.assertTrue(result["leftControls"], msg=json.dumps(result))
        self.assertTrue(result["workbenchControls"], msg=json.dumps(result))
        self.assertTrue(result["modeControls"], msg=json.dumps(result))
        self.assertIn("shellModeControls", result["tabbarSibling"], msg=json.dumps(result))
        self.assertIn("shellModeControls", result["workbenchSibling"], msg=json.dumps(result))
        self.assertEqual(result["workbenchParent"], "shellWorkbenchControls", msg=json.dumps(result))
        self.assertEqual(result["canvasParent"], "shellLeftControls", msg=json.dumps(result))
        self.assertEqual(result["secondaryGroups"], ["noteTaskGroup", "noteDataGroup"], msg=json.dumps(result))
        self.assertIn("toolbarGroupCommands", result["consoleParentClass"], msg=json.dumps(result))
        self.assertIn("toolbarGroupCanvas", result["resetParentClass"], msg=json.dumps(result))

    def test_top_toolbar_can_collapse_restore_and_persist(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_TOP_TOOLBAR_COLLAPSE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var header = document.querySelector('header');
      var toggle = document.getElementById('toggleHeaderTools');
      var expandedHeight = header.getBoundingClientRect().height;
      var initial = {
        collapsed:document.body.classList.contains('header-tools-collapsed'),
        expanded:toggle && toggle.getAttribute('aria-expanded'),
        actions:getComputedStyle(document.querySelector('.shellActionStack')).display
      };
      toggle.click();
      setTimeout(function(){
        var collapsedHeight = header.getBoundingClientRect().height;
        var collapsed = {
          bodyClass:document.body.classList.contains('header-tools-collapsed'),
          expanded:toggle.getAttribute('aria-expanded'),
          title:toggle.title,
          actions:getComputedStyle(document.querySelector('.shellActionStack')).display,
          canvas:getComputedStyle(document.getElementById('shellLeftControls')).display,
          meta:getComputedStyle(document.querySelector('.toolbarMeta')).display,
          modes:getComputedStyle(document.querySelector('.shellModeControls')).display,
          workbenches:getComputedStyle(document.getElementById('shellWorkbenchControls')).display,
          saved:localStorage.getItem('kyanbasu:header-tools-collapsed'),
          heightReduced:collapsedHeight < expandedHeight - 20
        };
        document.body.classList.remove('header-tools-collapsed');
        window.restoreHeaderToolsState();
        var restoredFromStorage = document.body.classList.contains('header-tools-collapsed');
        toggle.click();
        setTimeout(function(){
          var reopened = {
            bodyClass:document.body.classList.contains('header-tools-collapsed'),
            expanded:toggle.getAttribute('aria-expanded'),
            actions:getComputedStyle(document.querySelector('.shellActionStack')).display,
            saved:localStorage.getItem('kyanbasu:header-tools-collapsed')
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify({initial:initial, collapsed:collapsed, restoredFromStorage:restoredFromStorage, reopened:reopened});
          document.body.appendChild(pre);
        }, 40);
      }, 40);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertFalse(result["initial"]["collapsed"], msg=json.dumps(result))
        self.assertEqual(result["initial"]["expanded"], "true", msg=json.dumps(result))
        self.assertNotEqual(result["initial"]["actions"], "none", msg=json.dumps(result))
        self.assertTrue(result["collapsed"]["bodyClass"], msg=json.dumps(result))
        self.assertEqual(result["collapsed"]["expanded"], "false", msg=json.dumps(result))
        self.assertEqual(result["collapsed"]["title"], "Show tools", msg=json.dumps(result))
        self.assertEqual(result["collapsed"]["actions"], "none", msg=json.dumps(result))
        self.assertEqual(result["collapsed"]["canvas"], "none", msg=json.dumps(result))
        self.assertEqual(result["collapsed"]["meta"], "none", msg=json.dumps(result))
        self.assertNotEqual(result["collapsed"]["modes"], "none", msg=json.dumps(result))
        self.assertNotEqual(result["collapsed"]["workbenches"], "none", msg=json.dumps(result))
        self.assertEqual(result["collapsed"]["saved"], "1", msg=json.dumps(result))
        self.assertTrue(result["collapsed"]["heightReduced"], msg=json.dumps(result))
        self.assertTrue(result["restoredFromStorage"], msg=json.dumps(result))
        self.assertFalse(result["reopened"]["bodyClass"], msg=json.dumps(result))
        self.assertEqual(result["reopened"]["expanded"], "true", msg=json.dumps(result))
        self.assertNotEqual(result["reopened"]["actions"], "none", msg=json.dumps(result))
        self.assertEqual(result["reopened"]["saved"], "0", msg=json.dumps(result))

    def test_context_selection_bar_handles_note_and_link_actions(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CONTEXT_SELECTION_NOTES_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      function actions(){
        return Array.prototype.slice.call(document.querySelectorAll('#contextSelectionActions button')).map(function(b){ return b.getAttribute('data-context-action'); });
      }
      function clickAction(name){
        var btn = document.querySelector('#contextSelectionActions [data-context-action="'+name+'"]');
        if (!btn) throw new Error('missing context action ' + name);
        btn.click();
      }
      var a = window.KyanbasuNotes.createNote(180, 240, 'Alpha', '', 'Planning', {skipAutoLayout:true});
      var singleActions = actions();
      clickAction('note-child');
      var afterChild = window.KyanbasuNotes.notes().length;
      var b = window.KyanbasuNotes.createNote(780, 240, 'Beta', '', 'Planning', {skipAutoLayout:true});
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      var multiActions = actions();
      clickAction('note-task');
      var stagedTasks = (window.STAGED_CMDS || []).filter(function(line){ return String(line).indexOf('task add ') === 0; }).length;
      clickAction('note-link');
      var linkState = window.KyanbasuContextBar.state();
      var linkActions = actions();
      clickAction('link-delete');
      var out = {
        bar: !!document.getElementById('contextSelectionBar'),
        singleActions: singleActions,
        afterChild: afterChild,
        multiActions: multiActions,
        stagedTasks: stagedTasks,
        linkState: linkState,
        linkActions: linkActions,
        remainingLinks: window.KyanbasuNotes.links().length,
        hiddenAfterUnlink: document.getElementById('contextSelectionBar').hidden
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["bar"], msg=json.dumps(result))
        self.assertIn("note-child", result["singleActions"], msg=json.dumps(result))
        self.assertIn("note-sibling", result["singleActions"], msg=json.dumps(result))
        self.assertEqual(result["afterChild"], 2, msg=json.dumps(result))
        self.assertIn("note-link", result["multiActions"], msg=json.dumps(result))
        self.assertIn("note-task", result["multiActions"], msg=json.dumps(result))
        self.assertEqual(result["stagedTasks"], 2, msg=json.dumps(result))
        self.assertEqual(result["linkState"]["kind"], "link", msg=json.dumps(result))
        self.assertEqual(result["linkActions"], ["link-delete"], msg=json.dumps(result))
        self.assertEqual(result["remainingLinks"], 1, msg=json.dumps(result))
        self.assertTrue(result["hiddenAfterUnlink"], msg=json.dumps(result))

    def test_context_selection_bar_switches_between_tasks_and_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha task",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CONTEXT_SELECTION_TASKS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var task = (window.TASKS || [])[0];
      addNodeForTask(task, 180, 240, {deferLayout:true});
      var node = document.querySelector('#builderStage .node[data-short="aaaaaaaa"]');
      selectNode(node);
      var taskState = window.KyanbasuContextBar.state();
      var taskActions = Array.prototype.slice.call(document.querySelectorAll('#contextSelectionActions button')).map(function(b){ return b.getAttribute('data-context-action'); });
      document.querySelector('#contextSelectionActions [data-context-action="done"]').click();
      var note = window.KyanbasuNotes.createNote(620, 260, 'Planning note', '', 'Planning', {skipAutoLayout:true});
      var noteState = window.KyanbasuContextBar.state();
      var taskSelectedAfterNote = node.classList.contains('selected');
      selectNode(node);
      var finalState = window.KyanbasuContextBar.state();
      var out = {
        taskState: taskState,
        taskActions: taskActions,
        stagedDone: node.classList.contains('stagedDone'),
        noteState: noteState,
        taskSelectedAfterNote: taskSelectedAfterNote,
        finalState: finalState,
        selectedNotesAfterTask: window.KyanbasuNotes.selectedNotes().length
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["taskState"]["kind"], "task", msg=json.dumps(result))
        self.assertIn("locate", result["taskActions"], msg=json.dumps(result))
        self.assertIn("modify", result["taskActions"], msg=json.dumps(result))
        self.assertTrue(result["stagedDone"], msg=json.dumps(result))
        self.assertEqual(result["noteState"]["kind"], "note", msg=json.dumps(result))
        self.assertFalse(result["taskSelectedAfterNote"], msg=json.dumps(result))
        self.assertEqual(result["finalState"]["kind"], "task", msg=json.dumps(result))
        self.assertEqual(result["selectedNotesAfterTask"], 0, msg=json.dumps(result))

    def test_canvas_workbenches_switch_layouts_and_notes_without_clearing_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": ["next"],
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_WORKBENCHES_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.STAGED_CMDS = ['task aaaaaaaa modify +focus'];
      var task = (window.TASKS || [])[0];
      if (task && typeof addNodeForTask === 'function') addNodeForTask(task, 420, 280, {deferLayout:true});
      window.KyanbasuNotes.createNote(520, 360, 'Main note', '', 'Planning', {skipAutoLayout:true});
      window.KyanbasuWorkbenches.capture();
      var createdId = window.KyanbasuWorkbenches.create();
      window.KyanbasuWorkbenches.rename(createdId, 'Planning');
      setTimeout(function(){
        var afterCreate = {
          active: window.KyanbasuWorkbenches.active(),
          tabs: document.querySelectorAll('.tcWorkbenchTab').length,
          tabLabels: Array.prototype.slice.call(document.querySelectorAll('.tcWorkbenchTabName')).map(function(el){ return el.textContent; }),
          tabMeta: Array.prototype.slice.call(document.querySelectorAll('.tcWorkbenchTabMeta')).map(function(el){ return el.textContent; }),
          tabActions: document.querySelectorAll('.tcWorkbenchTabAction').length,
          list: window.KyanbasuWorkbenches.list(),
          nodes: document.querySelectorAll('#builderStage .node').length,
          notes: window.KyanbasuNotes.notes().length,
          commands: (window.STAGED_CMDS || []).slice()
        };
        window.KyanbasuWorkbenches.switchTo('main');
        setTimeout(function(){
          var duplicateId = window.KyanbasuWorkbenches.duplicate('main');
          var duplicated = window.KyanbasuWorkbenches.active();
          window.KyanbasuWorkbenches.switchTo('main');
          var duplicateSwitch = document.querySelector('[data-workbench-switch="' + duplicateId + '"]');
          if (duplicateSwitch) duplicateSwitch.click();
          var duplicatedClickActive = window.KyanbasuWorkbenches.active();
          window.KyanbasuWorkbenches.delete(duplicateId);
          window.KyanbasuWorkbenches.switchTo(createdId);
          var deleted = window.KyanbasuWorkbenches.delete(createdId);
          setTimeout(function(){
          var out = {
            group: !!document.getElementById('workbenchGroup'),
            api: !!window.KyanbasuWorkbenches,
            afterCreate: afterCreate,
            duplicated: duplicated,
            duplicatedClickActive: duplicatedClickActive,
            deleted: deleted,
            active: window.KyanbasuWorkbenches.active(),
            list: window.KyanbasuWorkbenches.list(),
            tabs: document.querySelectorAll('.tcWorkbenchTab').length,
            tabLabels: Array.prototype.slice.call(document.querySelectorAll('.tcWorkbenchTabName')).map(function(el){ return el.textContent; }),
            tabMeta: Array.prototype.slice.call(document.querySelectorAll('.tcWorkbenchTabMeta')).map(function(el){ return el.textContent; }),
            tabActions: document.querySelectorAll('.tcWorkbenchTabAction').length,
            nodes: document.querySelectorAll('#builderStage .node').length,
            notes: window.KyanbasuNotes.notes().length,
            noteContent: (window.KyanbasuNotes.notes()[0] || {}).content || '',
            commands: (window.STAGED_CMDS || []).slice()
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
          }, 260);
        }, 260);
      }, 260);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["group"], msg=json.dumps(result))
        self.assertTrue(result["api"], msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["active"]["name"], "Planning", msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["tabs"], 2, msg=json.dumps(result))
        self.assertIn("Planning", result["afterCreate"]["tabLabels"], msg=json.dumps(result))
        self.assertIn("1T 1N", result["afterCreate"]["tabMeta"], msg=json.dumps(result))
        self.assertIn("0T 0N", result["afterCreate"]["tabMeta"], msg=json.dumps(result))
        self.assertGreaterEqual(result["afterCreate"]["tabActions"], 5, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["list"][0]["tasks"], 1, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["list"][0]["notes"], 1, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["list"][1]["tasks"], 0, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["list"][1]["notes"], 0, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["nodes"], 0, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["notes"], 0, msg=json.dumps(result))
        self.assertEqual(result["afterCreate"]["commands"], ["task aaaaaaaa modify +focus"], msg=json.dumps(result))
        self.assertEqual(result["duplicated"]["name"], "Main copy", msg=json.dumps(result))
        self.assertEqual(result["duplicatedClickActive"]["id"], result["duplicated"]["id"], msg=json.dumps(result))
        self.assertTrue(result["deleted"], msg=json.dumps(result))
        self.assertEqual(result["active"]["id"], "main", msg=json.dumps(result))
        self.assertEqual(result["tabs"], 1, msg=json.dumps(result))
        self.assertEqual(result["tabLabels"], ["Main"], msg=json.dumps(result))
        self.assertEqual(result["tabMeta"], ["1T 1N"], msg=json.dumps(result))
        self.assertEqual(result["tabActions"], 2, msg=json.dumps(result))
        self.assertEqual(result["list"][0]["tasks"], 1, msg=json.dumps(result))
        self.assertEqual(result["list"][0]["notes"], 1, msg=json.dumps(result))
        self.assertEqual(result["nodes"], 1, msg=json.dumps(result))
        self.assertEqual(result["notes"], 1, msg=json.dumps(result))
        self.assertEqual(result["noteContent"], "Main note", msg=json.dumps(result))
        self.assertEqual(result["commands"], ["task aaaaaaaa modify +focus"], msg=json.dumps(result))

    def test_canvas_workbench_duplicate_reopens_after_canvas_changes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": ["next"],
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_WORKBENCH_DUPLICATE_REOPEN_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var task = (window.TASKS || [])[0];
      if (task && typeof addNodeForTask === 'function') addNodeForTask(task, 100, 120, {deferLayout:true});
      window.KyanbasuNotes.createNote(180, 220, 'Base note', '', 'Planning', {skipAutoLayout:true});
      window.KyanbasuWorkbenches.capture();
      var duplicateId = window.KyanbasuWorkbenches.duplicate('main');
      setTimeout(function(){
        var copyNote = window.KyanbasuNotes.createNote(520, 420, 'Copy-only note', '', 'Copy', {skipAutoLayout:true});
        var node = document.querySelector('#builderStage .node[data-short="aaaaaaaa"]');
        if (node){
          node.style.left = '680px';
          node.style.top = '520px';
        }
        window.KyanbasuWorkbenches.capture();
        window.KyanbasuWorkbenches.switchTo('main');
        setTimeout(function(){
          var mainBeforeClick = {
            active: window.KyanbasuWorkbenches.active(),
            notes: window.KyanbasuNotes.notes().map(function(n){ return n.content; }),
            nodeLeft: (document.querySelector('#builderStage .node[data-short="aaaaaaaa"]') || {}).style ? document.querySelector('#builderStage .node[data-short="aaaaaaaa"]').style.left : ''
          };
          var sw = document.querySelector('[data-workbench-switch="' + duplicateId + '"]');
          if (sw){
            sw.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
            sw.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
          }
          setTimeout(function(){
            var out = {
              duplicateId: duplicateId,
              clicked: !!sw,
              mainBeforeClick: mainBeforeClick,
              active: window.KyanbasuWorkbenches.active(),
              notes: window.KyanbasuNotes.notes().map(function(n){ return n.content; }).sort(),
              nodeLeft: (document.querySelector('#builderStage .node[data-short="aaaaaaaa"]') || {}).style ? document.querySelector('#builderStage .node[data-short="aaaaaaaa"]').style.left : '',
              tabLabels: Array.prototype.slice.call(document.querySelectorAll('.tcWorkbenchTabName')).map(function(el){ return el.textContent; })
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 320);
        }, 320);
      }, 320);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["clicked"], msg=json.dumps(result))
        self.assertEqual(result["mainBeforeClick"]["active"]["id"], "main", msg=json.dumps(result))
        self.assertEqual(result["mainBeforeClick"]["notes"], ["Base note"], msg=json.dumps(result))
        self.assertEqual(result["active"]["id"], result["duplicateId"], msg=json.dumps(result))
        self.assertEqual(result["notes"], ["Base note", "Copy-only note"], msg=json.dumps(result))
        self.assertEqual(result["nodeLeft"], "680px", msg=json.dumps(result))

    def test_canvas_workbench_export_all_includes_each_workbench_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": ["next"],
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_WORKBENCH_EXPORT_ALL_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var task = (window.TASKS || [])[0];
      if (task && typeof addNodeForTask === 'function') addNodeForTask(task, 100, 120, {deferLayout:true});
      window.KyanbasuNotes.createNote(180, 220, 'Main note', '', 'Planning', {skipAutoLayout:true});
      window.KyanbasuWorkbenches.capture();
      var secondId = window.KyanbasuWorkbenches.create();
      window.KyanbasuWorkbenches.rename(secondId, 'Delivery');
      setTimeout(function(){
        window.KyanbasuNotes.createNote(520, 360, 'Delivery note', '', 'Delivery', {skipAutoLayout:true});
        window.KyanbasuWorkbenches.capture();
        var current = JSON.parse(window.KyanbasuNotes.exportJSON());
        var all = window.KyanbasuWorkbenches.exportData();
        var noteCounts = all.workbenches.map(function(w){ return {name:w.name, notes:w.notes.notes.length, tasks:w.layout && w.layout.nodes ? Object.keys(w.layout.nodes).length : 0}; });
        var out = {
          currentKind: current.kind,
          currentNotes: current.notes.map(function(n){ return n.content; }).sort(),
          allKind: all.kind,
          activeId: all.activeId,
          workbenches: all.workbenches.length,
          noteCounts: noteCounts,
          button: !!document.getElementById('noteExportAllBtn')
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 320);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["button"], msg=json.dumps(result))
        self.assertEqual(result["currentKind"], "kyanbasu.notes", msg=json.dumps(result))
        self.assertEqual(result["currentNotes"], ["Delivery note"], msg=json.dumps(result))
        self.assertEqual(result["allKind"], "kyanbasu.workbenches", msg=json.dumps(result))
        self.assertEqual(result["workbenches"], 2, msg=json.dumps(result))
        self.assertEqual(result["noteCounts"][0]["name"], "Main", msg=json.dumps(result))
        self.assertEqual(result["noteCounts"][0]["notes"], 1, msg=json.dumps(result))
        self.assertEqual(result["noteCounts"][0]["tasks"], 1, msg=json.dumps(result))
        self.assertEqual(result["noteCounts"][1]["name"], "Delivery", msg=json.dumps(result))
        self.assertEqual(result["noteCounts"][1]["notes"], 1, msg=json.dumps(result))
        self.assertEqual(result["noteCounts"][1]["tasks"], 0, msg=json.dumps(result))

    def test_canvas_workbench_imports_taskcanvas_export_and_normalizes_kinds(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_WORKBENCH_IMPORT_ALL_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var backup = {
        kind: 'taskcanvas.workbenches',
        version: 1,
        activeId: 'delivery',
        nextIndex: 3,
        workbenches: [
          {
            id: 'main',
            name: 'Main',
            layout: {version:1, zoom:100, drawer_collapsed:true, nodes:{}, projects:[], tags:[]},
            notes: {
              kind:'taskcanvas.notes',
              version:1,
              notes:[{id:'main-note', x:180, y:220, content:'Imported main', bucket:'Planning'}],
              links:[],
              buckets:{Planning:{dx:0, dy:0, collapsed:false, followNotes:true, color:'blue'}}
            }
          },
          {
            id: 'delivery',
            name: 'Delivery',
            layout: {version:1, zoom:100, drawer_collapsed:true, nodes:{}, projects:[], tags:[]},
            notes: {
              kind:'taskcanvas.notes',
              version:1,
              notes:[{id:'delivery-note', x:520, y:360, content:'Imported delivery', bucket:'Delivery'}],
              links:[],
              buckets:{Delivery:{dx:0, dy:0, collapsed:false, followNotes:true, color:'green'}}
            }
          }
        ]
      };
      window.KyanbasuNotes.createNote(200, 200, 'Local note', '', 'Local', {skipAutoLayout:true});
      var imported = window.KyanbasuWorkbenches.importData(backup);
      setTimeout(function(){
        var deliveryNotes = window.KyanbasuNotes.notes().map(function(n){ return n.content; });
        window.KyanbasuWorkbenches.switchTo('main');
        setTimeout(function(){
          var mainNotes = window.KyanbasuNotes.notes().map(function(n){ return n.content; });
          var reexported = window.KyanbasuWorkbenches.exportData();
          var reexportedKinds = reexported.workbenches.map(function(w){ return w.notes.kind; });
          var out = {
            imported: imported,
            active: window.KyanbasuWorkbenches.active(),
            list: window.KyanbasuWorkbenches.list(),
            deliveryNotes: deliveryNotes,
            mainNotes: mainNotes,
            reexportedKind: reexported.kind,
            reexportedKinds: reexportedKinds
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 260);
      }, 260);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["imported"]["workbenches"], 2, msg=json.dumps(result))
        self.assertEqual(result["imported"]["activeId"], "delivery", msg=json.dumps(result))
        self.assertEqual(result["deliveryNotes"], ["Imported delivery"], msg=json.dumps(result))
        self.assertEqual(result["active"]["id"], "main", msg=json.dumps(result))
        self.assertEqual(result["mainNotes"], ["Imported main"], msg=json.dumps(result))
        self.assertEqual(result["reexportedKind"], "kyanbasu.workbenches", msg=json.dumps(result))
        self.assertEqual(result["reexportedKinds"], ["kyanbasu.notes", "kyanbasu.notes"], msg=json.dumps(result))
        self.assertEqual([w["name"] for w in result["list"]], ["Main", "Delivery"], msg=json.dumps(result))

    def test_canvas_navigator_renders_and_jumps_viewport(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NAVIGATOR_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var note = window.KyanbasuNotes.createNote(3200, 2100, "Remote note", "", "Planning", {skipAutoLayout:true});
      var task = document.createElement('div');
      task.className = 'node selected';
      task.setAttribute('data-short', 'T1');
      task.style.left = '1800px';
      task.style.top = '900px';
      task.style.width = '220px';
      task.style.height = '110px';
      task.textContent = 'Remote task';
      document.getElementById('builderStage').appendChild(task);
      window.KyanbasuNotes.selectNote(note.id);
      window.KyanbasuNavigator.render();
      setTimeout(function(){
        var panel = document.getElementById('tcNavigator');
        var cnv = panel && panel.querySelector('canvas');
        var cv = document.querySelector('#builderWrap .canvas');
        var selBtn = panel && panel.querySelector('[data-fit="selection"]');
        var before = {
          visible: !!panel && getComputedStyle(panel).display !== 'none',
          meta: panel ? panel.querySelector('.tcNavigatorMeta').textContent : '',
          selectionDisabled: selBtn ? selBtn.disabled : true,
          left: cv.scrollLeft,
          top: cv.scrollTop
        };
        var ms = window.KyanbasuNavigator.mapState('all');
        var x = ms.ox + ((note.x + 110) - ms.bounds.x) * ms.m;
        var y = ms.oy + ((note.y + 46) - ms.bounds.y) * ms.m;
        var cr = cnv.getBoundingClientRect();
        cnv.dispatchEvent(new MouseEvent('mousedown', {
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:cr.left + x * (cr.width / 234),
          clientY:cr.top + y * (cr.height / 150)
        }));
        document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0}));
        setTimeout(function(){
          var jumped = {left: cv.scrollLeft, top: cv.scrollTop};
          window.KyanbasuNavigator.fitTo('selection');
          setTimeout(function(){
            var out = {
              visible: before.visible,
              meta: before.meta,
              selectionDisabled: before.selectionDisabled,
              jumpedRight: jumped.left > before.left + 100,
              jumpedDown: jumped.top > before.top + 100,
              zoomAfterFit: document.getElementById('zoom').value,
              console: (document.getElementById('consoleText') || {}).value || ''
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 120);
        }, 80);
      }, 220);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["visible"], msg=json.dumps(result))
        self.assertIn("1 tasks", result["meta"], msg=json.dumps(result))
        self.assertIn("1 notes", result["meta"], msg=json.dumps(result))
        self.assertFalse(result["selectionDisabled"], msg=json.dumps(result))
        self.assertTrue(result["jumpedRight"], msg=json.dumps(result))
        self.assertTrue(result["jumpedDown"], msg=json.dumps(result))
        self.assertGreaterEqual(int(result["zoomAfterFit"]), 50, msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_navigator_can_be_dragged_and_restores_position(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NAVIGATOR_DRAG_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNavigator.render();
      setTimeout(function(){
        var panel = document.getElementById('tcNavigator');
        var head = panel.querySelector('.tcNavigatorHead');
        var r = panel.getBoundingClientRect();
        var hr = head.getBoundingClientRect();
        head.dispatchEvent(new MouseEvent('mousedown', {
          bubbles:true,
          cancelable:true,
          button:0,
          clientX:hr.left + 20,
          clientY:hr.top + 8
        }));
        document.dispatchEvent(new MouseEvent('mousemove', {
          bubbles:true,
          cancelable:true,
          clientX:hr.left + 100,
          clientY:hr.top - 58
        }));
        document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0}));
        setTimeout(function(){
          var moved = panel.getBoundingClientRect();
          var saved = JSON.parse(localStorage.getItem('kyanbasu:navigator:v1') || '{}');
          panel.remove();
          window.KyanbasuNavigator.render();
          setTimeout(function(){
            var restored = document.getElementById('tcNavigator').getBoundingClientRect();
            var out = {
              movedRight: moved.left > r.left + 50,
              movedUp: moved.top < r.top - 30,
              savedLeft: saved.left,
              savedTop: saved.top,
              restoredNearSaved: Math.abs(restored.left - saved.left) <= 2 && Math.abs(restored.top - saved.top) <= 2,
              rightAuto: document.getElementById('tcNavigator').style.right === 'auto',
              bottomAuto: document.getElementById('tcNavigator').style.bottom === 'auto',
              console: (document.getElementById('consoleText') || {}).value || ''
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
          }, 80);
        }, 80);
      }, 220);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["movedRight"], msg=json.dumps(result))
        self.assertTrue(result["movedUp"], msg=json.dumps(result))
        self.assertIsInstance(result["savedLeft"], int, msg=json.dumps(result))
        self.assertIsInstance(result["savedTop"], int, msg=json.dumps(result))
        self.assertTrue(result["restoredNearSaved"], msg=json.dumps(result))
        self.assertTrue(result["rightAuto"], msg=json.dumps(result))
        self.assertTrue(result["bottomAuto"], msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_navigator_keeps_stable_bounds_when_branch_collapses(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NAVIGATOR_COLLAPSE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var left = window.KyanbasuNotes.createNote(200, 240, "Left root", "", "", {skipAutoLayout:true});
      window.KyanbasuNotes.createChildNote(left.id, "Left child 1", "");
      window.KyanbasuNotes.createChildNote(left.id, "Left child 2", "");
      var right = window.KyanbasuNotes.createNote(2600, 1600, "Right root", "", "", {skipAutoLayout:true});
      window.KyanbasuNotes.createChildNote(right.id, "Right child 1", "");
      window.KyanbasuNotes.createChildNote(right.id, "Right child 2", "");
      window.KyanbasuNavigator.render();
      var before = window.KyanbasuNavigator.mapState('all').bounds;
      window.KyanbasuNotes.toggleCollapse(left.id);
      window.KyanbasuNavigator.render();
      var after = window.KyanbasuNavigator.mapState('all').bounds;
      var visible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){
        return el.style.display !== 'none';
      }).length;
      var out = {
        total: window.KyanbasuNotes.notes().length,
        visible: visible,
        meta: document.querySelector('#tcNavigator .tcNavigatorMeta').textContent,
        boundsStable: before.x === after.x && before.y === after.y && before.w === after.w && before.h === after.h,
        console: (document.getElementById('consoleText') || {}).value || ''
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 900);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["total"], 6, msg=json.dumps(result))
        self.assertEqual(result["visible"], 4, msg=json.dumps(result))
        self.assertIn("6 notes", result["meta"], msg=json.dumps(result))
        self.assertTrue(result["boundsStable"], msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_task_cards_render_polished_metadata(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_TASK_CARD_VISUALS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var ready = {uuid:"vis-ready", short:"VR", desc:"Ready task", project:"Design", tags:["UI"], has_depends:false, due:"20260601T000000Z"};
      var blocked = {uuid:"vis-blocked", short:"VB", desc:"Blocked task", project:"Delivery", tags:["Build"], has_depends:true};
      PARENT_DEPS0["VB"] = ["VR"];
      CHILD_TO_PARENTS["VR"] = ["VB"];
      addNodeForTask(ready, 180, 180, {deferLayout:true});
      addNodeForTask(blocked, 520, 180, {deferLayout:true});
      recomputeAreasAndTags();
      setTimeout(function(){
        var readyNode = document.querySelector('.node[data-short="VR"]');
        var blockedNode = document.querySelector('.node[data-short="VB"]');
        var proj = document.querySelector('.projArea[data-proj="Design"]');
        var tag = document.querySelector('.tagArea[data-tag="UI"]');
        var out = {
          readyClass: readyNode.className,
          blockedClass: blockedNode.className,
          readyStatus: readyNode.querySelector('.nodeStatePill').textContent,
          blockedStatus: blockedNode.querySelector('.nodeStatePill').textContent,
          chips: Array.prototype.slice.call(readyNode.querySelectorAll('.nodeChip')).map(function(el){ return el.textContent; }),
          blockedChips: Array.prototype.slice.call(blockedNode.querySelectorAll('.nodeChip')).map(function(el){ return el.textContent; }),
          shortBadges: document.querySelectorAll('#builderStage .node .nodeShortBadge').length,
          projectCount: proj ? proj.querySelector('.projAreaLabel') : null,
          projectLabelCount: (document.querySelector('.projAreaLabel[data-proj-label="Design"]') || {}).getAttribute && document.querySelector('.projAreaLabel[data-proj-label="Design"]').getAttribute('data-count'),
          tagLabelCount: (document.querySelector('.tagAreaLabel[data-tag-label="UI"]') || {}).getAttribute && document.querySelector('.tagAreaLabel[data-tag-label="UI"]').getAttribute('data-count'),
          nodeRadius: getComputedStyle(readyNode).borderRadius,
          projectRadius: proj ? getComputedStyle(proj).borderRadius : "",
          tagRadius: tag ? getComputedStyle(tag).borderRadius : "",
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertIn("ready", result["readyClass"], msg=json.dumps(result))
        self.assertIn("hasDeps", result["blockedClass"], msg=json.dumps(result))
        self.assertEqual(result["readyStatus"], "Ready", msg=json.dumps(result))
        self.assertEqual(result["blockedStatus"], "Blocked", msg=json.dumps(result))
        self.assertIn("Design", result["chips"], msg=json.dumps(result))
        self.assertIn("UI", result["chips"], msg=json.dumps(result))
        self.assertIn("2026-06-01", result["chips"], msg=json.dumps(result))
        self.assertNotIn("1 block", result["chips"], msg=json.dumps(result))
        self.assertNotIn("1 dep", result["blockedChips"], msg=json.dumps(result))
        self.assertEqual(result["shortBadges"], 0, msg=json.dumps(result))
        self.assertEqual(result["projectLabelCount"], "1", msg=json.dumps(result))
        self.assertEqual(result["tagLabelCount"], "1", msg=json.dumps(result))
        self.assertEqual(result["nodeRadius"], "12px", msg=json.dumps(result))
        self.assertEqual(result["projectRadius"], "20px", msg=json.dumps(result))
        self.assertEqual(result["tagRadius"], "16px", msg=json.dumps(result))
        self.assertEqual(result["console"], "", msg=json.dumps(result))

    def test_canvas_notes_create_linked_tasks_stages_and_links_generated_refs(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_CREATE_LINKED_TASKS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "Plan linked", "", "Planning");
      var b = window.KyanbasuNotes.createNote(440, 240, "Build linked", "details", "Delivery");
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      var count1 = window.KyanbasuNotes.createLinkedTasksFromSelectedNotes();
      var refsA1 = window.KyanbasuNotes.linkedTasks(a.id);
      var refsB1 = window.KyanbasuNotes.linkedTasks(b.id);
      var count2 = window.KyanbasuNotes.createLinkedTasksFromSelectedNotes();
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var lines = ((document.getElementById('consoleText') || {}).value || "").split(/\\n/).filter(Boolean);
        var badgeA = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"] .tcNoteTaskBadge');
        var exported = window.KyanbasuNotes.exportData();
        var noteA = exported.notes.filter(function(n){ return n.id === a.id; })[0];
        var out = {
          button: !!document.getElementById('noteCreateLinkedTasksBtn'),
          count1: count1,
          count2: count2,
          refsA1: refsA1,
          refsA2: window.KyanbasuNotes.linkedTasks(a.id),
          refsB1: refsB1,
          lines: lines,
          staged: Array.isArray(window.STAGED_CMDS) ? window.STAGED_CMDS.slice() : [],
          badgeAText: badgeA && badgeA.textContent,
          exportedRefsA: noteA && noteA.taskRefs
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["button"], msg=json.dumps(result))
        self.assertEqual(result["count1"], 2, msg=json.dumps(result))
        self.assertEqual(result["count2"], 2, msg=json.dumps(result))
        self.assertEqual(len(result["refsA1"]), 1, msg=json.dumps(result))
        self.assertEqual(result["refsA1"], result["refsA2"], msg=json.dumps(result))
        self.assertEqual(len(result["refsB1"]), 1, msg=json.dumps(result))
        self.assertTrue(result["refsA1"][0]["uuid"].startswith("new-note-"), msg=json.dumps(result))
        self.assertTrue(result["refsA1"][0]["short"].startswith("n-"), msg=json.dumps(result))
        self.assertEqual(result["refsA1"][0]["desc"], "Plan linked", msg=json.dumps(result))
        self.assertEqual(result["refsB1"][0]["desc"], "Build linked\ndetails", msg=json.dumps(result))
        self.assertEqual(len(result["staged"]), 2, msg=json.dumps(result))
        self.assertEqual(len(result["lines"]), 2, msg=json.dumps(result))
        self.assertIn("task add 'Plan linked'", result["lines"])
        self.assertIn("task add 'Build linked details'", result["lines"])
        self.assertEqual(result["badgeAText"], "1 task", msg=json.dumps(result))
        self.assertEqual(result["exportedRefsA"], result["refsA1"], msg=json.dumps(result))

    def test_console_editor_edits_and_removes_commands_across_updates(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CONSOLE_EDITOR_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      try{
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: { writeText: function(txt){ window.__copiedText = txt; return Promise.resolve(); } }
        });
      }catch(_){}
      var a = window.KyanbasuNotes.createNote(180, 240, "First task", "");
      var b = window.KyanbasuNotes.createNote(440, 240, "Second task", "");
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      window.KyanbasuNotes.stageSelectedNotesAsTasks();
      setTimeout(function(){
        var rows = document.querySelectorAll('#consoleRows .consoleCommandRow');
        rows[0].querySelector('button').click();
        var input = rows[0].querySelector('.consoleCommandEdit');
        input.value = "task add Edited first +next";
        rows[0].querySelectorAll('button')[0].click();
        setTimeout(function(){
          var rows2 = document.querySelectorAll('#consoleRows .consoleCommandRow');
          rows2[1].querySelectorAll('button')[1].click();
          if (typeof updateConsole === 'function') updateConsole();
          setTimeout(function(){
            var text = (document.getElementById('consoleText') || {}).value || "";
            var review = window.KyanbasuReview.current();
            document.getElementById('copyBtn').click();
            setTimeout(function(){
            var out = {
              rowCount: document.querySelectorAll('#consoleRows .consoleCommandRow').length,
              rowsInOverlay: !!(document.getElementById('consoleRows') && document.getElementById('depCmdPre') && document.getElementById('consoleRows').nextSibling === document.getElementById('depCmdPre')),
              textareaBacking: document.getElementById('consoleText').classList.contains('consoleEditorBacking'),
              overlayBacking: document.getElementById('depCmdPre').classList.contains('consoleEditorBacking'),
              text: text,
              copied: window.__copiedText || "",
              reviewText: review.text,
              reviewNewTasks: review.groups.newTasks.length,
              stateEdits: Object.keys(window.KyanbasuConsoleEditor.state().edits).length,
              stateRemoved: Object.keys(window.KyanbasuConsoleEditor.state().removed).length
            };
            var pre = document.createElement('pre');
            pre.id = 'e2e-out';
            pre.textContent = JSON.stringify(out);
            document.body.appendChild(pre);
            }, 60);
          }, 220);
        }, 120);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["rowCount"], 1)
        self.assertTrue(result["rowsInOverlay"])
        self.assertTrue(result["textareaBacking"])
        self.assertTrue(result["overlayBacking"])
        self.assertEqual(result["text"], "task add Edited first +next")
        self.assertEqual(result["copied"], "task add Edited first +next")
        self.assertEqual(result["reviewText"], "task add Edited first +next")
        self.assertEqual(result["reviewNewTasks"], 1)
        self.assertEqual(result["stateEdits"], 1)
        self.assertEqual(result["stateRemoved"], 1)

    def test_console_update_immediately_displays_short_ids_without_uuid_flicker(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": ["next"],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 1, lambda *_: None)

        harness = """
<script id="E2E_CONSOLE_SHORT_ID_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.EX_OPS = window.EX_OPS || {};
      window.EX_OPS["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"] = {done:true};
      updateConsole();
      var immediate = (document.getElementById('consoleText') || {}).value || "";
      setTimeout(function(){
        var later = (document.getElementById('consoleText') || {}).value || "";
        var out = {
          immediate: immediate,
          later: later,
          immediateHasUuid: immediate.indexOf("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") !== -1,
          immediateHasShort: immediate.indexOf("'aaaaaaaa'") !== -1,
          stable: immediate === later
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 180);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 800);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertFalse(result["immediateHasUuid"], msg=json.dumps(result))
        self.assertTrue(result["immediateHasShort"], msg=json.dumps(result))
        self.assertEqual(result["immediate"], "task 'aaaaaaaa' done", msg=json.dumps(result))
        self.assertTrue(result["stable"], msg=json.dumps(result))

    def test_console_editor_mounts_empty_state_without_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CONSOLE_EDITOR_EMPTY_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var rows = document.getElementById('consoleRows');
      var ta = document.getElementById('consoleText');
      var out = {
        api: !!window.KyanbasuConsoleEditor,
        rows: !!rows,
        rowsInOverlay: !!(rows && document.getElementById('depCmdPre') && rows.nextSibling === document.getElementById('depCmdPre')),
        empty: !!document.querySelector('#consoleRows .consoleCommandEmpty'),
        emptyText: (document.querySelector('#consoleRows .consoleCommandEmpty') || {}).textContent || "",
        textareaBacking: !!(ta && ta.classList.contains('consoleEditorBacking')),
        overlayBacking: !!(document.getElementById('depCmdPre') && document.getElementById('depCmdPre').classList.contains('consoleEditorBacking')),
        rowCount: document.querySelectorAll('#consoleRows .consoleCommandRow').length
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 500);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["api"])
        self.assertTrue(result["rows"])
        self.assertTrue(result["rowsInOverlay"])
        self.assertTrue(result["empty"])
        self.assertEqual(result["emptyText"], "No pending commands")
        self.assertTrue(result["textareaBacking"])
        self.assertTrue(result["overlayBacking"])
        self.assertEqual(result["rowCount"], 0)

    def test_canvas_notes_runtime_creates_child_branches_and_reflows_map(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_MINDMAP_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Launch plan", "");
      var a = window.KyanbasuNotes.createChildNote(root.id, "Design", "");
      var b = window.KyanbasuNotes.createChildNote(root.id, "Build", "");
      var c = window.KyanbasuNotes.createChildNote(a.id, "Prototype", "");
      window.KyanbasuNotes.reflowMindMap(root.id);
      window.KyanbasuNotes.save();
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var links = window.KyanbasuNotes.links();
        var byContent = {};
        notes.forEach(function(n){ byContent[n.content] = n; });
        var out = {
          reflowButton: !!document.getElementById('noteReflowBtn'),
          reflowText: (document.getElementById('noteReflowBtn') || {}).textContent || "",
          actionButtons: document.querySelectorAll('.tcNoteNode [data-note-child]').length,
          cardLinkButtons: document.querySelectorAll('.tcNoteNode [data-note-link]').length,
          notes: notes.length,
          childLinks: links.filter(function(l){ return l.type === 'child'; }).length,
          childPaths: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink[data-type="child"]').length,
          designRightOfRoot: byContent.Design.x > byContent["Launch plan"].x,
          prototypeRightOfDesign: byContent.Prototype.x > byContent.Design.x,
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 80);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["reflowButton"])
        self.assertEqual(result["reflowText"], "Compact map")
        self.assertEqual(result["actionButtons"], 4)
        self.assertEqual(result["cardLinkButtons"], 0)
        self.assertEqual(result["notes"], 4)
        self.assertEqual(result["childLinks"], 3)
        self.assertEqual(result["childPaths"], 3)
        self.assertTrue(result["designRightOfRoot"])
        self.assertTrue(result["prototypeRightOfDesign"])
        self.assertEqual(result["console"], "")

    def test_canvas_notes_rejects_invalid_child_graph_mutations(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BRANCH_GUARDS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, 'Root', '');
      var child = window.KyanbasuNotes.createChildNote(root.id, 'Child', '');
      var nested = window.KyanbasuNotes.createChildNote(child.id, 'Nested', '');
      var other = window.KyanbasuNotes.createNote(900, 240, 'Other', '');
      var cycle = window.KyanbasuNotes.linkNotes(nested.id, root.id, 'child');
      var cycleMessage = (document.getElementById('devConsoleToast') || {}).textContent || '';
      var secondParent = window.KyanbasuNotes.linkNotes(other.id, child.id, 'child');
      var parentMessage = (document.getElementById('devConsoleToast') || {}).textContent || '';
      var out = {
        cycle: cycle,
        cycleMessage: cycleMessage,
        secondParent: secondParent,
        parentMessage: parentMessage,
        selfParent: window.KyanbasuNotes.linkNotes(root.id, root.id, 'child'),
        duplicate: window.KyanbasuNotes.linkNotes(root.id, child.id, 'child'),
        manualCycle: window.KyanbasuNotes.linkNotes(nested.id, root.id, 'manual'),
        childLinks: window.KyanbasuNotes.links().filter(function(l){ return l.type === 'child'; }).length,
        manualLinks: window.KyanbasuNotes.links().filter(function(l){ return l.type === 'manual'; }).length
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertFalse(result["cycle"], msg=json.dumps(result))
        self.assertEqual(result["cycleMessage"], "This child link would create a cycle.", msg=json.dumps(result))
        self.assertFalse(result["secondParent"], msg=json.dumps(result))
        self.assertEqual(result["parentMessage"], "This note already has a parent.", msg=json.dumps(result))
        self.assertFalse(result["selfParent"], msg=json.dumps(result))
        self.assertFalse(result["duplicate"], msg=json.dumps(result))
        self.assertTrue(result["manualCycle"], msg=json.dumps(result))
        self.assertEqual(result["childLinks"], 2, msg=json.dumps(result))
        self.assertEqual(result["manualLinks"], 1, msg=json.dumps(result))

    def test_canvas_notes_import_repairs_invalid_child_graph(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BRANCH_IMPORT_GUARDS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var result = window.KyanbasuNotes.importData({
        kind:'kyanbasu.notes',
        version:1,
        notes:[
          {id:'a', x:180, y:240, content:'A'},
          {id:'b', x:480, y:240, content:'B'},
          {id:'c', x:780, y:240, content:'C'},
          {id:'d', x:180, y:520, content:'D'}
        ],
        links:[
          {from:'a', to:'b', type:'child'},
          {from:'b', to:'c', type:'child'},
          {from:'c', to:'a', type:'child'},
          {from:'d', to:'b', type:'child'},
          {from:'a', to:'a', type:'child'},
          {from:'missing', to:'d', type:'child'},
          {from:'a', to:'d', type:'child'},
          {from:'a', to:'d', type:'manual'},
          {from:'d', to:'c', type:'manual'}
        ]
      });
      var out = {
        result: result,
        links: window.KyanbasuNotes.links().map(function(l){ return l.type + ':' + l.from + ':' + l.to; }).sort(),
        outlineRoots: window.KyanbasuNotes.outline().map(function(n){ return n.id; }).sort()
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["result"]["notes"], 4, msg=json.dumps(result))
        self.assertEqual(result["result"]["links"], 4, msg=json.dumps(result))
        self.assertEqual(result["result"]["droppedLinks"], 5, msg=json.dumps(result))
        self.assertEqual(result["result"]["droppedChildLinks"], 4, msg=json.dumps(result))
        self.assertEqual(
            result["links"],
            ["child:a:b", "child:a:d", "child:b:c", "manual:d:c"],
            msg=json.dumps(result),
        )
        self.assertEqual(result["outlineRoots"], ["a"], msg=json.dumps(result))

    def test_canvas_notes_load_repairs_and_persists_invalid_child_graph(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"workspace_id": "branch-storage-guards", "tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_BRANCH_STORAGE_GUARDS_HARNESS">
(function(){
  var storageKey = 'kyanbasu:workspace:v1:branch-storage-guards:notes';
  localStorage.setItem(storageKey, JSON.stringify({
    notes:[
      {id:'a', x:180, y:240, content:'A'},
      {id:'b', x:480, y:240, content:'B'},
      {id:'c', x:780, y:240, content:'C'}
    ],
    links:[
      {from:'a', to:'b', type:'child'},
      {from:'b', to:'a', type:'child'},
      {from:'c', to:'b', type:'child'},
      {from:'missing', to:'c', type:'child'}
    ]
  }));
  window.addEventListener('load', function(){
    setTimeout(function(){
      try{
        var stableKey = window.KyanbasuStorage.key('notes');
        var persisted = JSON.parse(localStorage.getItem(stableKey) || '{}');
        var out = {
          runtimeLinks: window.KyanbasuNotes.links().map(function(l){ return l.from + ':' + l.to; }),
          persistedLinks: (persisted.links || []).map(function(l){ return l.from + ':' + l.to; }),
          notes: window.KyanbasuNotes.notes().length,
          stableKey: stableKey,
          repairToast: (document.getElementById('devConsoleToast') || {}).textContent || ''
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }catch(e){
        var pre2 = document.createElement('pre');
        pre2.id = 'e2e-out';
        pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
        document.body.appendChild(pre2);
      }
    }, 700);
  });
})();
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["notes"], 3, msg=json.dumps(result))
        self.assertEqual(result["runtimeLinks"], ["a:b"], msg=json.dumps(result))
        self.assertEqual(result["persistedLinks"], ["a:b"], msg=json.dumps(result))
        self.assertTrue(result["stableKey"].startswith("kyanbasu:workspace:v1:"), msg=json.dumps(result))
        self.assertEqual(result["repairToast"], "Repaired 3 invalid saved note links.", msg=json.dumps(result))

    def test_canvas_notes_shows_saving_and_saved_status(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_SAVE_STATUS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var status = document.getElementById('noteSaveStatus');
      var initial = status ? status.textContent : '';
      window.KyanbasuNotes.createNote(180, 240, 'Save status', '');
      var pending = status ? status.textContent : '';
      setTimeout(function(){
        var out = {
          initial: initial,
          pending: pending,
          saved: status ? status.textContent : '',
          state: status ? status.getAttribute('data-state') : '',
          parent: status && status.parentElement ? status.parentElement.id : ''
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 260);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["initial"], "Saved", msg=json.dumps(result))
        self.assertEqual(result["pending"], "Saving...", msg=json.dumps(result))
        self.assertEqual(result["saved"], "Saved", msg=json.dumps(result))
        self.assertEqual(result["state"], "saved", msg=json.dumps(result))
        self.assertEqual(result["parent"], "noteDataGroup", msg=json.dumps(result))

    def test_canvas_notes_compact_map_packs_bucket_groups(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_COMPACT_MAP_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(120, 240, "Alpha root", "", "Planning", {skipAutoLayout:true});
      window.KyanbasuNotes.createChildNote(a.id, "Alpha child", "");
      var b = window.KyanbasuNotes.createNote(2500, 900, "Beta root", "", "Delivery", {skipAutoLayout:true});
      window.KyanbasuNotes.createChildNote(b.id, "Beta child", "");
      var c = window.KyanbasuNotes.createNote(4200, 1600, "Gamma root", "", "Review", {skipAutoLayout:true});
      function rects(){
        return Array.prototype.slice.call(document.querySelectorAll('.tcNoteBucket')).map(function(el){
          return {
            bucket: el.getAttribute('data-bucket'),
            x: parseFloat(el.style.left || '0'),
            y: parseFloat(el.style.top || '0'),
            w: parseFloat(el.style.width || '0'),
            h: parseFloat(el.style.height || '0')
          };
        });
      }
      function span(rs){
        var minX = Math.min.apply(null, rs.map(function(r){ return r.x; }));
        var maxX = Math.max.apply(null, rs.map(function(r){ return r.x + r.w; }));
        var minY = Math.min.apply(null, rs.map(function(r){ return r.y; }));
        var maxY = Math.max.apply(null, rs.map(function(r){ return r.y + r.h; }));
        return {w:maxX-minX, h:maxY-minY};
      }
      function overlap(a, b){
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
      }
      setTimeout(function(){
        var before = rects();
        var beforeSpan = span(before);
        window.KyanbasuNotes.compactMindMap();
        setTimeout(function(){
          var after = rects();
          var afterSpan = span(after);
          var overlaps = false;
          for (var i=0;i<after.length;i++) for (var j=i+1;j<after.length;j++) if (overlap(after[i], after[j])) overlaps = true;
          var notes = window.KyanbasuNotes.notes();
          var byContent = {};
          notes.forEach(function(n){ byContent[n.content] = n; });
          var out = {
            beforeSpan: beforeSpan,
            afterSpan: afterSpan,
            buckets: after.length,
            overlaps: overlaps,
            alphaChildRight: byContent["Alpha child"].x > byContent["Alpha root"].x,
            betaChildRight: byContent["Beta child"].x > byContent["Beta root"].x,
            buttonText: (document.getElementById('noteReflowBtn') || {}).textContent || ""
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 120);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["buttonText"], "Compact map", msg=json.dumps(result))
        self.assertEqual(result["buckets"], 3, msg=json.dumps(result))
        self.assertFalse(result["overlaps"], msg=json.dumps(result))
        self.assertLess(result["afterSpan"]["w"], result["beforeSpan"]["w"], msg=json.dumps(result))
        self.assertLess(result["afterSpan"]["h"], result["beforeSpan"]["h"], msg=json.dumps(result))
        self.assertTrue(result["alphaChildRight"], msg=json.dumps(result))
        self.assertTrue(result["betaChildRight"], msg=json.dumps(result))

    def test_canvas_notes_compact_map_avoids_task_project_space(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_COMPACT_AVOIDS_TASKS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var task = {short:"1", uuid:"task-1", desc:"Important task", project:"Work", tags:["next"]};
      window.TASKS = window.TASKS || [];
      window.TASKS.push(task);
      window.TASK_BY_SHORT = window.TASK_BY_SHORT || {};
      window.TASK_BY_SHORT[task.short] = task;
      addNodeForTask(task, 160, 140, {deferLayout:true});
      recomputeAreasAndTags();
      var a = window.KyanbasuNotes.createNote(2600, 240, "Alpha root", "", "Planning", {skipAutoLayout:true});
      window.KyanbasuNotes.createChildNote(a.id, "Alpha child", "");
      var b = window.KyanbasuNotes.createNote(3300, 620, "Beta root", "", "Review", {skipAutoLayout:true});
      function rectFor(el){
        return {
          x: parseFloat(el.style.left || '0'),
          y: parseFloat(el.style.top || '0'),
          w: parseFloat(el.style.width || el.offsetWidth || '0'),
          h: parseFloat(el.style.height || el.offsetHeight || '0')
        };
      }
      function overlap(a, b){
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
      }
      setTimeout(function(){
        window.KyanbasuNotes.compactMindMap();
        setTimeout(function(){
          var buckets = Array.prototype.slice.call(document.querySelectorAll('.tcNoteBucket')).map(rectFor);
          var occupied = Array.prototype.slice.call(document.querySelectorAll('#builderStage .node, #builderStage .projArea, #builderStage .tagArea')).map(rectFor);
          var overlaps = false;
          buckets.forEach(function(bucket){
            occupied.forEach(function(rect){
              if (overlap(bucket, rect)) overlaps = true;
            });
          });
          var out = {
            buckets: buckets.length,
            occupied: occupied.length,
            overlaps: overlaps,
            firstBucketX: buckets[0] ? buckets[0].x : null,
            projectRight: occupied.reduce(function(max, r){ return Math.max(max, r.x + r.w); }, 0)
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 120);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["buckets"], 2, msg=json.dumps(result))
        self.assertGreaterEqual(result["occupied"], 3, msg=json.dumps(result))
        self.assertFalse(result["overlaps"], msg=json.dumps(result))

    def test_canvas_notes_keyboard_creates_sibling_and_child_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_KEYBOARD_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Root", "");
      var first = window.KyanbasuNotes.createChildNote(root.id, "First", "");
      window.KyanbasuNotes.selectNote(first.id);
      document.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
      if (document.activeElement) document.activeElement.blur();
      window.KyanbasuNotes.selectNote(first.id);
      document.dispatchEvent(new KeyboardEvent('keydown', {key:'Tab', bubbles:true, cancelable:true}));
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var links = window.KyanbasuNotes.links();
        var byContent = {};
        notes.forEach(function(n){
          if (!byContent[n.content]) byContent[n.content] = [];
          byContent[n.content].push(n);
        });
        var root = byContent.Root && byContent.Root[0];
        var firstNote = byContent.First && byContent.First[0];
        var newNotes = notes.filter(function(n){ return root && firstNote && n.id !== root.id && n.id !== firstNote.id; });
        newNotes.sort(function(a, b){ return (a.x - b.x) || (a.y - b.y); });
        var sibling = newNotes.filter(function(n){ return firstNote && Math.abs(n.x - firstNote.x) < 80 && n.y > firstNote.y + 80; })[0] || null;
        var child = newNotes.filter(function(n){ return firstNote && n.x > firstNote.x + 220 && Math.abs(n.y - firstNote.y) < 120; })[0] || null;
        var rootChildren = links.filter(function(l){ return l.type === 'child' && l.from === root.id; });
        var firstChildren = links.filter(function(l){ return l.type === 'child' && l.from === first.id; });
        var selected = document.querySelectorAll('.tcNoteNode.selected').length;
        var out = {
          notes: notes.length,
          links: links.length,
          childLinks: links.filter(function(l){ return l.type === 'child'; }).length,
          rootChildren: rootChildren.length,
          firstChildren: firstChildren.length,
          siblingBelow: !!(sibling && firstNote && sibling.y > firstNote.y + 80),
          childRight: !!(child && firstNote && child.x > firstNote.x + 220),
          selected: selected,
          focusedText: !!(document.activeElement && document.activeElement.classList && document.activeElement.classList.contains('tcNoteText')),
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["notes"], 4)
        self.assertEqual(result["links"], 3)
        self.assertEqual(result["childLinks"], 3)
        self.assertEqual(result["rootChildren"], 2)
        self.assertEqual(result["firstChildren"], 1)
        self.assertTrue(result["siblingBelow"])
        self.assertTrue(result["childRight"])
        self.assertEqual(result["selected"], 1)
        self.assertTrue(result["focusedText"])
        self.assertEqual(result["console"], "")

    def test_canvas_notes_dynamic_reference_labels_follow_mind_map(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_LABELS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "Root A", "", "Planning", {skipAutoLayout: true});
      var b = window.KyanbasuNotes.createNote(620, 240, "Root B", "", "Planning", {skipAutoLayout: true});
      var aChild = window.KyanbasuNotes.createChildNote(a.id, "A child", "");
      var aNested = window.KyanbasuNotes.createChildNote(aChild.id, "A nested", "");
      var aSibling = window.KyanbasuNotes.createSiblingNote(aChild.id, "A sibling", "");
      setTimeout(function(){
        var labels = window.KyanbasuNotes.noteLabels();
        function badge(id){
          var el = document.querySelector('.tcNoteNode[data-note-id="'+id+'"] .tcNoteCode');
          return el ? el.textContent : "";
        }
        var exported = window.KyanbasuNotes.exportData();
        var out = {
          labels: {
            a: labels[a.id],
            b: labels[b.id],
            aChild: labels[aChild.id],
            aSibling: labels[aSibling.id],
            aNested: labels[aNested.id]
          },
          badges: {
            a: badge(a.id),
            b: badge(b.id),
            aChild: badge(aChild.id),
            aSibling: badge(aSibling.id),
            aNested: badge(aNested.id)
          },
          exportedHasGeneratedLabel: exported.notes.some(function(n){
            return Object.prototype.hasOwnProperty.call(n, 'label') ||
              Object.prototype.hasOwnProperty.call(n, 'code') ||
              Object.prototype.hasOwnProperty.call(n, 'reference');
          })
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["labels"]["a"], "A1", msg=json.dumps(result))
        self.assertEqual(result["labels"]["b"], "B1", msg=json.dumps(result))
        self.assertEqual(result["labels"]["aChild"], "A1-1", msg=json.dumps(result))
        self.assertEqual(result["labels"]["aSibling"], "A1-2", msg=json.dumps(result))
        self.assertEqual(result["labels"]["aNested"], "A1-1-1", msg=json.dumps(result))
        self.assertEqual(result["badges"], result["labels"], msg=json.dumps(result))
        self.assertFalse(result["exportedHasGeneratedLabel"], msg=json.dumps(result))

    def test_canvas_notes_search_matches_label_text_and_bucket(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_SEARCH_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Planning root", "", "Planning", {skipAutoLayout: true});
      var child = window.KyanbasuNotes.createChildNote(root.id, "Risk register", "");
      var delivery = window.KyanbasuNotes.createNote(620, 260, "Ship checklist", "", "Delivery", {skipAutoLayout: true});
      var input = document.getElementById('noteSearchInput');
      function runQuery(q){
        input.value = q;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        return {
          ids: window.KyanbasuNotes.searchNotes(q),
          resultCodes: Array.prototype.slice.call(document.querySelectorAll('#noteSearchResults .tcNoteSearchCode')).map(function(el){ return el.textContent; }),
          highlighted: Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode.searchMatch')).map(function(el){ return el.getAttribute('data-note-id'); })
        };
      }
      var byLabel = runQuery('A1-1');
      var byText = runQuery('risk');
      var byBucket = runQuery('delivery');
      input.value = 'A1-1';
      input.dispatchEvent(new Event('input', {bubbles:true}));
      input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
      setTimeout(function(){
        var out = {
          hasInput: !!input,
          byLabel: byLabel,
          byText: byText,
          byBucket: byBucket,
          selected: window.KyanbasuNotes.selectedNotes(),
          childId: child.id,
          deliveryId: delivery.id,
          resultsVisible: !document.getElementById('noteSearchResults').hidden
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["hasInput"], msg=json.dumps(result))
        self.assertIn(result["childId"], result["byLabel"]["ids"], msg=json.dumps(result))
        self.assertIn("A1-1", result["byLabel"]["resultCodes"], msg=json.dumps(result))
        self.assertIn(result["childId"], result["byLabel"]["highlighted"], msg=json.dumps(result))
        self.assertIn(result["childId"], result["byText"]["ids"], msg=json.dumps(result))
        self.assertIn(result["deliveryId"], result["byBucket"]["ids"], msg=json.dumps(result))
        self.assertEqual(result["selected"], [result["childId"]], msg=json.dumps(result))
        self.assertTrue(result["resultsVisible"], msg=json.dumps(result))

    def test_canvas_notes_structured_queries_and_thinking_lenses(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_LENS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var openQuestion = KyanbasuNotes.createNote(140, 180, 'What blocks launch?', '', 'Deep Work', {skipAutoLayout:true, kind:'question'});
      var resolvedQuestion = KyanbasuNotes.createNote(380, 180, 'Who owns launch?', '', 'Deep Work', {skipAutoLayout:true, kind:'question', status:'resolved'});
      var assumption = KyanbasuNotes.createNote(620, 180, 'Users need export', '', 'Research', {skipAutoLayout:true, kind:'assumption'});
      var action = KyanbasuNotes.createNote(860, 180, 'Draft rollout', '', 'Delivery', {skipAutoLayout:true, kind:'action'});
      var decision = KyanbasuNotes.createNote(1100, 180, 'Use phased rollout', '', 'Delivery', {skipAutoLayout:true, kind:'decision'});
      var queries = {
        openQuestions: KyanbasuNotes.searchNotes('kind:question status:open'),
        quotedBucket: KyanbasuNotes.searchNotes('bucket:"Deep Work"'),
        unresolved: KyanbasuNotes.searchNotes('kind:question -status:resolved'),
        textAndKind: KyanbasuNotes.searchNotes('launch kind:question'),
        orphans: KyanbasuNotes.searchNotes('is:orphan'),
        withoutTasks: KyanbasuNotes.searchNotes('-has:tasks')
      };
      document.getElementById('noteLensBtn').click();
      var menuOptions = document.querySelectorAll('#noteLensMenu .tcNoteLensOption').length;
      KyanbasuNotes.applyLens('open-questions');
      renderViewer();
      var lensVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).map(function(el){ return el.getAttribute('data-note-id'); });
      var viewerRows = Array.prototype.slice.call(document.querySelectorAll('#viewerStage .viewerNote')).map(function(el){ return el.getAttribute('data-note-id'); });
      var viewerTitle = document.querySelector('#viewerStage .viewerSection:last-of-type .viewerSectionTitle');
      KyanbasuNotes.applyLens('actions');
      var actionBeforeLink = KyanbasuNotes.lensState();
      KyanbasuNotes.linkNoteToTask(action.id, {uuid:'task-1', short:'task-1', desc:'Draft rollout'});
      var actionAfterLink = KyanbasuNotes.lensState();
      KyanbasuNotes.clearLens();
      var visibleAfterClear = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length;
      var out = {
        ids:{openQuestion:openQuestion.id, resolvedQuestion:resolvedQuestion.id, action:action.id},
        queries:queries,
        menuOptions:menuOptions,
        lensVisible:lensVisible,
        viewerRows:viewerRows,
        viewerTitle:viewerTitle && viewerTitle.textContent,
        actionBeforeLink:actionBeforeLink,
        actionAfterLink:actionAfterLink,
        visibleAfterClear:visibleAfterClear,
        totalNotes:KyanbasuNotes.notes().length,
        parsed:KyanbasuNotes.parseSearchQuery('kind:question -status:resolved bucket:"Deep Work"')
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        ids = result["ids"]
        self.assertEqual(result["queries"]["openQuestions"], [ids["openQuestion"]], msg=json.dumps(result))
        self.assertEqual(set(result["queries"]["quotedBucket"]), {ids["openQuestion"], ids["resolvedQuestion"]}, msg=json.dumps(result))
        self.assertEqual(result["queries"]["unresolved"], [ids["openQuestion"]], msg=json.dumps(result))
        self.assertEqual(set(result["queries"]["textAndKind"]), {ids["openQuestion"], ids["resolvedQuestion"]}, msg=json.dumps(result))
        self.assertEqual(len(result["queries"]["orphans"]), result["totalNotes"], msg=json.dumps(result))
        self.assertEqual(len(result["queries"]["withoutTasks"]), result["totalNotes"], msg=json.dumps(result))
        self.assertEqual(result["menuOptions"], 8, msg=json.dumps(result))
        self.assertEqual(result["lensVisible"], [ids["openQuestion"]], msg=json.dumps(result))
        self.assertEqual(result["viewerRows"], [ids["openQuestion"]], msg=json.dumps(result))
        self.assertIn("Open questions", result["viewerTitle"], msg=json.dumps(result))
        self.assertEqual(result["actionBeforeLink"]["ids"], [ids["action"]], msg=json.dumps(result))
        self.assertEqual(result["actionAfterLink"]["ids"], [], msg=json.dumps(result))
        self.assertEqual(result["visibleAfterClear"], result["totalNotes"], msg=json.dumps(result))
        self.assertEqual([term["field"] for term in result["parsed"]], ["kind", "status", "bucket"], msg=json.dumps(result))
        self.assertTrue(result["parsed"][1]["negated"], msg=json.dumps(result))

    def test_canvas_notes_saved_custom_lenses_lifecycle(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_SAVED_LENS_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var matching = KyanbasuNotes.createNote(180, 220, 'Validate pricing', '', 'Research', {skipAutoLayout:true, kind:'assumption'});
      KyanbasuNotes.createNote(460, 220, 'Draft pricing page', '', 'Delivery', {skipAutoLayout:true, kind:'action'});
      var saved = KyanbasuNotes.saveLens('Research assumptions', 'bucket:Research kind:assumption status:open');
      var duplicate = KyanbasuNotes.saveLens('research assumptions', 'kind:action');
      var applied = KyanbasuNotes.applyLens(saved.id);
      var activeBeforeRename = KyanbasuNotes.lensState();
      var renamed = KyanbasuNotes.renameLens(saved.id, 'Open research assumptions');
      var activeAfterRename = KyanbasuNotes.lensState();
      document.getElementById('noteLensBtn').click();
      var customRow = document.querySelector('#noteLensMenu .tcNoteLensRow.custom');
      var menuText = customRow && customRow.textContent;
      var stored = KyanbasuStorage.getJSON('note-lenses', []);
      var deleted = KyanbasuNotes.deleteLens(saved.id);
      var out = {
        saved:saved,
        duplicate:duplicate,
        applied:applied,
        activeBeforeRename:activeBeforeRename,
        renamed:renamed,
        activeAfterRename:activeAfterRename,
        menuText:menuText,
        stored:stored,
        deleted:deleted,
        lensAfterDelete:KyanbasuNotes.lensState(),
        definitions:KyanbasuNotes.lenses(),
        visible:Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length,
        matchingId:matching.id
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["saved"]["custom"], msg=json.dumps(result))
        self.assertIsNone(result["duplicate"], msg=json.dumps(result))
        self.assertTrue(result["applied"], msg=json.dumps(result))
        self.assertEqual(result["activeBeforeRename"]["ids"], [result["matchingId"]], msg=json.dumps(result))
        self.assertTrue(result["renamed"], msg=json.dumps(result))
        self.assertEqual(result["activeAfterRename"]["label"], "Open research assumptions", msg=json.dumps(result))
        self.assertIn("Open research assumptions", result["menuText"], msg=json.dumps(result))
        self.assertEqual(result["stored"][0]["label"], "Open research assumptions", msg=json.dumps(result))
        self.assertTrue(result["deleted"], msg=json.dumps(result))
        self.assertEqual(result["lensAfterDelete"]["kind"], "none", msg=json.dumps(result))
        self.assertEqual(len(result["definitions"]), 8, msg=json.dumps(result))
        self.assertEqual(result["visible"], 2, msg=json.dumps(result))

    def test_canvas_notes_review_metadata_queries_and_export(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_REVIEW_METADATA_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var now = Date.now();
      var day = 86400000;
      KyanbasuNotes.importData({notes:[
        {id:'stale-open', content:'Old open assumption', bucket:'Research', kind:'assumption', status:'open', createdAt:now-60*day, updatedAt:now-45*day, reviewedAt:now-40*day},
        {id:'fresh-reviewed', content:'Fresh decision', bucket:'Planning', kind:'decision', status:'open', createdAt:now-10*day, updatedAt:now-2*day, reviewedAt:now-day},
        {id:'never-recent', content:'Recent question', bucket:'Research', kind:'question', status:'open', createdAt:now-day, updatedAt:now-day, reviewedAt:0},
        {id:'old-resolved', content:'Closed history', bucket:'Archive', kind:'note', status:'resolved', createdAt:now-90*day, updatedAt:now-60*day, reviewedAt:0}
      ], links:[], buckets:{}});
      var queries = {
        never:KyanbasuNotes.searchNotes('reviewed:never'),
        recentReview:KyanbasuNotes.searchNotes('reviewed:7d'),
        recentUpdate:KyanbasuNotes.searchNotes('updated:7d'),
        stale:KyanbasuNotes.searchNotes('is:stale')
      };
      KyanbasuNotes.selectNote('never-recent');
      renderInspector();
      var inspectorText = document.getElementById('inspectorBody').textContent;
      KyanbasuNotes.startReview();
      var firstReviewId = KyanbasuNotes.reviewState().currentId;
      KyanbasuNotes.nextReview();
      var firstAfterNavigation = KyanbasuNotes.notes().filter(function(note){ return note.id === firstReviewId; })[0].reviewedAt;
      KyanbasuNotes.stopReview();
      var beforeUpdated = KyanbasuNotes.notes().filter(function(note){ return note.id === 'never-recent'; })[0].updatedAt;
      KyanbasuNotes.markReviewed('never-recent');
      var marked = KyanbasuNotes.notes().filter(function(note){ return note.id === 'never-recent'; })[0];
      var exported = KyanbasuNotes.exportData();
      var exportedMarked = exported.notes.filter(function(note){ return note.id === 'never-recent'; })[0];
      var out = {
        queries:queries,
        inspectorText:inspectorText,
        firstAfterNavigation:firstAfterNavigation,
        beforeUpdated:beforeUpdated,
        marked:marked,
        neverAfterMark:KyanbasuNotes.searchNotes('reviewed:never'),
        exportedVersion:exported.version,
        exportedMarked:exportedMarked,
        lensIds:KyanbasuNotes.lenses().map(function(lens){ return lens.id; })
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(set(result["queries"]["never"]), {"never-recent", "old-resolved"}, msg=json.dumps(result))
        self.assertEqual(result["queries"]["recentReview"], ["fresh-reviewed"], msg=json.dumps(result))
        self.assertEqual(set(result["queries"]["recentUpdate"]), {"fresh-reviewed", "never-recent"}, msg=json.dumps(result))
        self.assertEqual(result["queries"]["stale"], ["stale-open"], msg=json.dumps(result))
        self.assertIn("Never reviewed", result["inspectorText"], msg=json.dumps(result))
        self.assertEqual(result["firstAfterNavigation"], 0, msg=json.dumps(result))
        self.assertGreater(result["marked"]["reviewedAt"], 0, msg=json.dumps(result))
        self.assertEqual(result["marked"]["updatedAt"], result["beforeUpdated"], msg=json.dumps(result))
        self.assertNotIn("never-recent", result["neverAfterMark"], msg=json.dumps(result))
        self.assertEqual(result["exportedVersion"], 7, msg=json.dumps(result))
        self.assertEqual(result["exportedMarked"]["reviewedAt"], result["marked"]["reviewedAt"], msg=json.dumps(result))
        self.assertIn("never-reviewed", result["lensIds"], msg=json.dumps(result))
        self.assertIn("stale-open", result["lensIds"], msg=json.dumps(result))

    def test_canvas_notes_review_session_tracks_active_lens_and_actions(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_REVIEW_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var first = KyanbasuNotes.createNote(180, 220, 'First question', '', 'Research', {skipAutoLayout:true, kind:'question'});
      var second = KyanbasuNotes.createNote(460, 220, 'Second question', '', 'Research', {skipAutoLayout:true, kind:'question'});
      var third = KyanbasuNotes.createNote(740, 220, 'Background evidence', '', 'Research', {skipAutoLayout:true, kind:'evidence'});
      KyanbasuNotes.applyLens('open-questions');
      var started = KyanbasuNotes.startReview();
      var initial = KyanbasuNotes.reviewState();
      var initialPanel = !document.getElementById('tcNoteReviewPanel').hidden;
      document.querySelector('#tcNoteReviewPanel [data-review-status="resolved"]').click();
      var afterResolve = KyanbasuNotes.reviewState();
      var firstAfterResolve = KyanbasuNotes.notes().filter(function(note){ return note.id === first.id; })[0];
      var firstStatus = firstAfterResolve.status;
      document.querySelector('#tcNoteReviewPanel [data-review-kind="action"]').click();
      var afterActions = KyanbasuNotes.reviewState();
      var secondKind = KyanbasuNotes.notes().filter(function(note){ return note.id === second.id; })[0].kind;
      var secondReviewedAt = KyanbasuNotes.notes().filter(function(note){ return note.id === second.id; })[0].reviewedAt;
      var panelClosed = document.getElementById('tcNoteReviewPanel').hidden;
      KyanbasuNotes.clearLens();
      KyanbasuNotes.startReview();
      KyanbasuNotes.nextReview();
      var afterNext = KyanbasuNotes.reviewState();
      var editor = document.querySelector('#tcNoteReviewPanel .tcNoteReviewContent');
      editor.value = 'Edited during review';
      editor.dispatchEvent(new Event('input', {bubbles:true}));
      var edited = KyanbasuNotes.notes().filter(function(note){ return note.id === afterNext.currentId; })[0].content;
      KyanbasuNotes.previousReview();
      var afterPrevious = KyanbasuNotes.reviewState();
      KyanbasuNotes.stopReview();
      var out = {
        ids:{first:first.id, second:second.id, third:third.id},
        started:started,
        initial:initial,
        initialPanel:initialPanel,
        afterResolve:afterResolve,
        firstStatus:firstStatus,
        firstReviewedAt:firstAfterResolve.reviewedAt,
        afterActions:afterActions,
        secondKind:secondKind,
        secondReviewedAt:secondReviewedAt,
        panelClosed:panelClosed,
        afterNext:afterNext,
        edited:edited,
        afterPrevious:afterPrevious,
        stopped:KyanbasuNotes.reviewState()
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["started"], msg=json.dumps(result))
        self.assertTrue(result["initialPanel"], msg=json.dumps(result))
        self.assertEqual(result["initial"]["count"], 2, msg=json.dumps(result))
        self.assertEqual(result["initial"]["currentId"], result["ids"]["first"], msg=json.dumps(result))
        self.assertEqual(result["firstStatus"], "resolved", msg=json.dumps(result))
        self.assertGreater(result["firstReviewedAt"], 0, msg=json.dumps(result))
        self.assertEqual(result["afterResolve"]["count"], 1, msg=json.dumps(result))
        self.assertEqual(result["afterResolve"]["currentId"], result["ids"]["second"], msg=json.dumps(result))
        self.assertEqual(result["secondKind"], "action", msg=json.dumps(result))
        self.assertGreater(result["secondReviewedAt"], 0, msg=json.dumps(result))
        self.assertFalse(result["afterActions"]["active"], msg=json.dumps(result))
        self.assertTrue(result["panelClosed"], msg=json.dumps(result))
        self.assertEqual(result["afterNext"]["index"], 1, msg=json.dumps(result))
        self.assertEqual(result["edited"], "Edited during review", msg=json.dumps(result))
        self.assertEqual(result["afterPrevious"]["index"], 0, msg=json.dumps(result))
        self.assertFalse(result["stopped"]["active"], msg=json.dumps(result))

    def test_canvas_notes_links_selected_note_to_existing_task(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({
            "tasks": [
                {
                    "uuid": "task-alpha-uuid",
                    "short": "alpha",
                    "desc": "Alpha implementation",
                    "project": "Work",
                    "tags": ["next"],
                    "has_depends": False,
                }
            ],
            "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
        })
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_TASK_LINK_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var note = window.KyanbasuNotes.createNote(180, 240, "Plan Alpha", "", "Planning", {skipAutoLayout: true});
      var task = window.TASK_BY_SHORT && window.TASK_BY_SHORT.alpha;
      var node = window.addNodeForTask(task, 540, 240, {deferLayout:true});
      window.KyanbasuNotes.selectNote(note.id);
      document.getElementById('noteTaskLinkBtn').click();
      node.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0}));
      setTimeout(function(){
        var refs = window.KyanbasuNotes.linkedTasks(note.id);
        var exported = window.KyanbasuNotes.exportData();
        var noteOut = exported.notes.filter(function(n){ return n.id === note.id; })[0];
        var badge = document.querySelector('.tcNoteNode[data-note-id="'+note.id+'"] .tcNoteTaskBadge');
        var badgeText = badge && badge.textContent;
        var badgeHidden = badge && badge.hidden;
        badge.click();
        var popover = document.getElementById('tcNoteTaskPopover');
        var focusBtn = popover && popover.querySelector('[data-task-focus]');
        if (focusBtn) focusBtn.click();
        var highlightedFromMenu = node.classList.contains('noteTaskLinked');
        var unlinkBtn = popover && popover.querySelector('[data-task-unlink]');
        if (unlinkBtn) unlinkBtn.click();
        var refsAfterUnlink = window.KyanbasuNotes.linkedTasks(note.id);
        var exportedAfterUnlink = window.KyanbasuNotes.exportData();
        var noteAfterUnlink = exportedAfterUnlink.notes.filter(function(n){ return n.id === note.id; })[0];
        var out = {
          refs: refs,
          exportedRefs: noteOut && noteOut.taskRefs,
          badgeText: badgeText,
          badgeHidden: badgeHidden,
          nodeUuid: node.getAttribute('data-uuid'),
          popoverRows: popover ? popover.querySelectorAll('.tcNoteTaskRow').length : 0,
          highlighted: highlightedFromMenu,
          refsAfterUnlink: refsAfterUnlink,
          exportedRefsAfterUnlink: noteAfterUnlink && noteAfterUnlink.taskRefs,
          badgeAfterUnlink: badge && badge.textContent,
          badgeHiddenAfterUnlink: badge && badge.hidden,
          selectedNote: window.KyanbasuNotes.selectedNotes()
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 160);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(len(result["refs"]), 1, msg=json.dumps(result))
        self.assertEqual(result["refs"][0]["uuid"], "task-alpha-uuid", msg=json.dumps(result))
        self.assertEqual(result["refs"][0]["short"], "alpha", msg=json.dumps(result))
        self.assertEqual(result["refs"][0]["desc"], "Alpha implementation", msg=json.dumps(result))
        self.assertEqual(result["exportedRefs"], result["refs"], msg=json.dumps(result))
        self.assertEqual(result["badgeText"], "1 task", msg=json.dumps(result))
        self.assertFalse(result["badgeHidden"], msg=json.dumps(result))
        self.assertEqual(result["nodeUuid"], "task-alpha-uuid", msg=json.dumps(result))
        self.assertEqual(result["popoverRows"], 1, msg=json.dumps(result))
        self.assertTrue(result["highlighted"], msg=json.dumps(result))
        self.assertEqual(result["refsAfterUnlink"], [], msg=json.dumps(result))
        self.assertEqual(result["exportedRefsAfterUnlink"], [], msg=json.dumps(result))
        self.assertEqual(result["badgeAfterUnlink"], "", msg=json.dumps(result))
        self.assertTrue(result["badgeHiddenAfterUnlink"], msg=json.dumps(result))
        self.assertEqual(len(result["selectedNote"]), 1, msg=json.dumps(result))

    def test_canvas_inspector_renders_note_selection_and_actions(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_NOTE_INSPECTOR_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Plan Alpha", "", "Planning", {skipAutoLayout:true});
      window.KyanbasuNotes.selectNote(root.id);
      setTimeout(function(){
        var before = {
          title:(document.getElementById('inspectorTitle') || {}).textContent || '',
          sub:(document.getElementById('inspectorSub') || {}).textContent || '',
          done:(document.getElementById('inspectorDone') || {}).textContent || '',
          modify:(document.getElementById('inspectorModify') || {}).textContent || '',
          body:(document.getElementById('inspectorBody') || {}).textContent || '',
          editor:(document.getElementById('inspectorNoteContent') || {}).value || '',
          bucket:(document.getElementById('inspectorNoteBucket') || {}).value || ''
        };
        var editor = document.getElementById('inspectorNoteContent');
        editor.value = 'Plan Alpha updated';
        editor.dispatchEvent(new Event('input', {bubbles:true}));
        var bucketInput = document.getElementById('inspectorNoteBucket');
        bucketInput.value = 'Delivery';
        bucketInput.dispatchEvent(new Event('change', {bubbles:true}));
        var editedNote = window.KyanbasuNotes.notes().filter(function(n){ return n.id === root.id; })[0] || {};
        var cardText = (document.querySelector('.tcNoteNode[data-note-id="'+root.id+'"] .tcNoteText') || {}).textContent || '';
        var cardBucket = (document.querySelector('.tcNoteNode[data-note-id="'+root.id+'"] .tcNoteBucketLabel') || {}).textContent || '';
        document.getElementById('inspectorDone').click();
        setTimeout(function(){
          var notes = window.KyanbasuNotes.notes();
          var selected = window.KyanbasuNotes.selectedNotes();
          var selectedNote = notes.filter(function(n){ return n.id === selected[0]; })[0] || {};
          var after = {
            title:(document.getElementById('inspectorTitle') || {}).textContent || '',
            sub:(document.getElementById('inspectorSub') || {}).textContent || '',
            done:(document.getElementById('inspectorDone') || {}).textContent || '',
            modify:(document.getElementById('inspectorModify') || {}).textContent || '',
            body:(document.getElementById('inspectorBody') || {}).textContent || ''
          };
          var out = {
            before:before,
            after:after,
            notes:notes.length,
            links:window.KyanbasuNotes.links().length,
            selected:selected.length,
            selectedContent:selectedNote.content || '',
            editedContent:editedNote.content || '',
            editedBucket:editedNote.bucket || '',
            cardText:cardText,
            cardBucket:cardBucket
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 120);
      }, 80);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["before"]["title"], "A1 selected", msg=json.dumps(result))
        self.assertEqual(result["before"]["sub"], "Plan Alpha", msg=json.dumps(result))
        self.assertEqual(result["before"]["done"], "Child", msg=json.dumps(result))
        self.assertEqual(result["before"]["modify"], "Sibling", msg=json.dumps(result))
        self.assertEqual(result["before"]["editor"], "Plan Alpha", msg=json.dumps(result))
        self.assertEqual(result["before"]["bucket"], "Planning", msg=json.dumps(result))
        self.assertIn("Planning", result["before"]["body"], msg=json.dumps(result))
        self.assertEqual(result["editedContent"], "Plan Alpha updated", msg=json.dumps(result))
        self.assertEqual(result["editedBucket"], "Delivery", msg=json.dumps(result))
        self.assertEqual(result["cardText"], "Plan Alpha updated", msg=json.dumps(result))
        self.assertEqual(result["cardBucket"], "Delivery", msg=json.dumps(result))
        self.assertEqual(result["notes"], 2, msg=json.dumps(result))
        self.assertEqual(result["links"], 1, msg=json.dumps(result))
        self.assertEqual(result["selected"], 1, msg=json.dumps(result))
        self.assertEqual(result["selectedContent"], "New branch", msg=json.dumps(result))
        self.assertEqual(result["after"]["title"], "A1-1 selected", msg=json.dumps(result))

    def test_canvas_notes_tab_places_child_right_and_pushes_blocker(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_TAB_PLACEMENT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Root", "", "Planning", {skipAutoLayout: true});
      var blocker = window.KyanbasuNotes.createNote(root.x + 300, root.y, "Blocker", "", "Planning", {skipAutoLayout: true});
      var blockerStartX = blocker.x;
      window.KyanbasuNotes.createNote(root.x + 300, root.y + 220, "Other bucket", "", "Delivery", {skipAutoLayout: true});
      window.KyanbasuNotes.selectNote(root.id);
      document.dispatchEvent(new KeyboardEvent('keydown', {key:'Tab', bubbles:true, cancelable:true}));
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var links = window.KyanbasuNotes.links();
        var childIds = {};
        links.filter(function(l){ return l.type === 'child' && l.from === root.id; }).forEach(function(l){ childIds[l.to] = true; });
        var child = notes.filter(function(n){ return childIds[n.id]; })[0];
        var blockerAfter = notes.filter(function(n){ return n.id === blocker.id; })[0];
        var out = {
          childX: child && child.x,
          childY: child && child.y,
          sourceX: root.x,
          sourceY: root.y,
          childRightNear: !!(child && Math.abs(child.x - (root.x + 300)) < 16),
          childSameRow: !!(child && Math.abs(child.y - root.y) < 16),
          pushedBlockerRight: !!(blockerAfter && blockerAfter.x > blockerStartX + 80),
          sameBucket: !!(child && child.bucket === 'Planning')
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 140);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["childRightNear"], msg=json.dumps(result))
        self.assertTrue(result["childSameRow"], msg=json.dumps(result))
        self.assertTrue(result["pushedBlockerRight"], msg=json.dumps(result))
        self.assertTrue(result["sameBucket"], msg=json.dumps(result))

    def test_canvas_notes_enter_places_sibling_below_not_far_right(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_SIBLING_PLACEMENT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Root", "", "Planning");
      var first = window.KyanbasuNotes.createChildNote(root.id, "First", "");
      window.KyanbasuNotes.createNote(first.x + 360, first.y + 12, "Right side", "", "Planning");
      window.KyanbasuNotes.createNote(first.x + 260, first.y + 8, "Other bucket", "", "Delivery");
      var lower = window.KyanbasuNotes.createNote(first.x, first.y + 132, "Lower", "", "Planning", {skipAutoLayout: true});
      var lowerStartY = lower.y;
      window.KyanbasuNotes.selectNote(first.id);
      document.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var links = window.KyanbasuNotes.links();
        var siblingIds = {};
        links.filter(function(l){ return l.type === 'child' && l.from === root.id; }).forEach(function(l){ siblingIds[l.to] = true; });
        var sibling = notes.filter(function(n){ return siblingIds[n.id] && n.id !== first.id; }).sort(function(a, b){ return b.y - a.y; })[0];
        var lowerAfter = notes.filter(function(n){ return n.id === lower.id; })[0];
        var out = {
          siblingX: sibling && sibling.x,
          siblingY: sibling && sibling.y,
          sourceX: first.x,
          sourceY: first.y,
          below: !!(sibling && sibling.y > first.y + 80),
          insertedNearSource: !!(sibling && Math.abs(sibling.y - (first.y + 132)) < 16),
          pushedLowerDown: !!(lowerAfter && lowerAfter.y > lowerStartY + 80),
          sameColumn: !!(sibling && Math.abs(sibling.x - first.x) < 80),
          notFarRight: !!(sibling && sibling.x < first.x + 160),
          sameBucket: !!(sibling && sibling.bucket === 'Planning')
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 140);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["below"], msg=json.dumps(result))
        self.assertTrue(result["insertedNearSource"], msg=json.dumps(result))
        self.assertTrue(result["pushedLowerDown"], msg=json.dumps(result))
        self.assertTrue(result["sameColumn"], msg=json.dumps(result))
        self.assertTrue(result["notFarRight"], msg=json.dumps(result))
        self.assertTrue(result["sameBucket"], msg=json.dumps(result))

    def test_canvas_notes_multiselect_deletes_selected_notes_and_links(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_MULTISELECT_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Root", "");
      var a = window.KyanbasuNotes.createChildNote(root.id, "A", "");
      var b = window.KyanbasuNotes.createChildNote(root.id, "B", "");
      var c = window.KyanbasuNotes.createChildNote(a.id, "C", "");
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(c.id, true);
      document.dispatchEvent(new KeyboardEvent('keydown', {key:'Delete', bubbles:true, cancelable:true}));
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var notes = window.KyanbasuNotes.notes();
        var links = window.KyanbasuNotes.links();
        var out = {
          notes: notes.length,
          contents: notes.map(function(n){ return n.content; }).sort(),
          links: links.length,
          selected: window.KyanbasuNotes.selectedNotes().length,
          selectedNodes: document.querySelectorAll('.tcNoteNode.selected').length,
          domNotes: document.querySelectorAll('.tcNoteNode').length,
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["notes"], 2)
        self.assertEqual(result["contents"], ["B", "Root"])
        self.assertEqual(result["links"], 1)
        self.assertEqual(result["selected"], 0)
        self.assertEqual(result["selectedNodes"], 0)
        self.assertEqual(result["domNotes"], 2)
        self.assertEqual(result["console"], "")

    def test_canvas_inspector_moves_multiple_notes_to_bucket(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_MULTI_BUCKET_INSPECTOR_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "A", "", "Planning", {skipAutoLayout:true});
      var b = window.KyanbasuNotes.createNote(440, 240, "B", "", "Delivery", {skipAutoLayout:true});
      var c = window.KyanbasuNotes.createNote(760, 240, "C", "", "Later", {skipAutoLayout:true});
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      setTimeout(function(){
        var before = {
          title:(document.getElementById('inspectorTitle') || {}).textContent || '',
          label:document.querySelector('.inspectorLabel:nth-of-type(1)') ? document.querySelector('.inspectorLabel:nth-of-type(1)').textContent : '',
          bucket:(document.getElementById('inspectorNoteBucketSelect') || {}).value || '',
          bucketPlaceholder:(document.querySelector('#inspectorNoteBucketSelect option[value=""]') || {}).textContent || '',
          newHidden:(document.getElementById('inspectorNoteBucket') || {}).hidden,
          placeholder:(document.getElementById('inspectorNoteBucket') || {}).getAttribute('placeholder') || '',
          options:Array.prototype.slice.call(document.querySelectorAll('#inspectorNoteBucketSelect option')).map(function(el){ return el.value; }).filter(function(v){ return v && v !== '__new__'; }).sort(),
          newOption:!!document.querySelector('#inspectorNoteBucketSelect option[value="__new__"]'),
          reset:!!document.querySelector('[data-note-color="bucket"]'),
          swatches:document.querySelectorAll('[data-note-color]').length
        };
        var colorBtn = document.querySelector('[data-note-color="#2fbf71"]');
        if (colorBtn) colorBtn.click();
        var bucketInput = document.getElementById('inspectorNoteBucket');
        setTimeout(function(){
          var colorA = (document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]') || {}).style.getPropertyValue('--note-accent').trim();
          var colorB = (document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]') || {}).style.getPropertyValue('--note-accent').trim();
          var colorC = (document.querySelector('.tcNoteNode[data-note-id="'+c.id+'"]') || {}).style.getPropertyValue('--note-accent').trim();
          var exportedAfterColor = window.KyanbasuNotes.exportData();
          var exportedByContent = {};
          (exportedAfterColor.notes || []).forEach(function(n){ exportedByContent[n.content] = n; });
          var bucketSelect = document.getElementById('inspectorNoteBucketSelect');
          bucketSelect.value = 'Later';
          bucketSelect.dispatchEvent(new Event('change', {bubbles:true}));
          setTimeout(function(){
          var afterExisting = {};
          window.KyanbasuNotes.notes().forEach(function(n){ afterExisting[n.content] = n.bucket; });
          var resetBtn = document.querySelector('[data-note-color="bucket"]');
          if (resetBtn) resetBtn.click();
          setTimeout(function(){
          var exportedAfterReset = window.KyanbasuNotes.exportData();
          var resetByContent = {};
          (exportedAfterReset.notes || []).forEach(function(n){ resetByContent[n.content] = n; });
          bucketSelect = document.getElementById('inspectorNoteBucketSelect');
          bucketSelect.value = '__new__';
          bucketSelect.dispatchEvent(new Event('change', {bubbles:true}));
          bucketInput = document.getElementById('inspectorNoteBucket');
          bucketInput.value = 'Shared';
          bucketInput.dispatchEvent(new Event('change', {bubbles:true}));
          setTimeout(function(){
          var notes = window.KyanbasuNotes.notes();
          var byContent = {};
          notes.forEach(function(n){ byContent[n.content] = n; });
          var out = {
            before:before,
            colors:{
              A:colorA,
              B:colorB,
              C:colorC,
              exportedA:exportedByContent.A && exportedByContent.A.color || null,
              exportedB:exportedByContent.B && exportedByContent.B.color || null,
              exportedC:exportedByContent.C && exportedByContent.C.color || null,
              planning:exportedAfterColor.buckets && exportedAfterColor.buckets.Planning && exportedAfterColor.buckets.Planning.color,
              delivery:exportedAfterColor.buckets && exportedAfterColor.buckets.Delivery && exportedAfterColor.buckets.Delivery.color,
              later:exportedAfterColor.buckets && exportedAfterColor.buckets.Later && exportedAfterColor.buckets.Later.color
            },
            afterExisting: afterExisting,
            resetColors:{
              A: resetByContent.A && resetByContent.A.color || null,
              B: resetByContent.B && resetByContent.B.color || null
            },
            newInputVisible: !(document.getElementById('inspectorNoteBucket') || {}).hidden,
            buckets: {
              A: byContent.A && byContent.A.bucket,
              B: byContent.B && byContent.B.bucket,
              C: byContent.C && byContent.C.bucket
            },
            selected: window.KyanbasuNotes.selectedNotes().length,
            selectedNodes: document.querySelectorAll('.tcNoteNode.selected').length,
            cardBuckets: Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode.selected .tcNoteBucketLabel')).map(function(el){ return el.textContent; }).sort()
          };
          var pre = document.createElement('pre');
          pre.id = 'e2e-out';
          pre.textContent = JSON.stringify(out);
          document.body.appendChild(pre);
        }, 160);
        }, 120);
        }, 120);
        }, 160);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["before"]["title"], "2 notes selected", msg=json.dumps(result))
        self.assertEqual(result["before"]["bucket"], "", msg=json.dumps(result))
        self.assertEqual(result["before"]["bucketPlaceholder"], "Mixed buckets", msg=json.dumps(result))
        self.assertTrue(result["before"]["newHidden"], msg=json.dumps(result))
        self.assertEqual(result["before"]["placeholder"], "New bucket name", msg=json.dumps(result))
        self.assertEqual(result["before"]["options"], ["Delivery", "Later", "Planning"], msg=json.dumps(result))
        self.assertTrue(result["before"]["newOption"], msg=json.dumps(result))
        self.assertTrue(result["before"]["reset"], msg=json.dumps(result))
        self.assertGreater(result["before"]["swatches"], 0, msg=json.dumps(result))
        self.assertEqual(result["colors"]["A"], "#2fbf71", msg=json.dumps(result))
        self.assertEqual(result["colors"]["B"], "#2fbf71", msg=json.dumps(result))
        self.assertNotEqual(result["colors"]["C"], "#2fbf71", msg=json.dumps(result))
        self.assertEqual(result["colors"]["exportedA"], "#2fbf71", msg=json.dumps(result))
        self.assertEqual(result["colors"]["exportedB"], "#2fbf71", msg=json.dumps(result))
        self.assertIsNone(result["colors"]["exportedC"], msg=json.dumps(result))
        self.assertNotEqual(result["colors"]["planning"], "#2fbf71", msg=json.dumps(result))
        self.assertNotEqual(result["colors"]["delivery"], "#2fbf71", msg=json.dumps(result))
        self.assertNotEqual(result["colors"]["later"], "#2fbf71", msg=json.dumps(result))
        self.assertEqual(result["afterExisting"], {"A": "Later", "B": "Later", "C": "Later"}, msg=json.dumps(result))
        self.assertEqual(result["resetColors"], {"A": None, "B": None}, msg=json.dumps(result))
        self.assertFalse(result["newInputVisible"], msg=json.dumps(result))
        self.assertEqual(result["buckets"], {"A": "Shared", "B": "Shared", "C": "Later"}, msg=json.dumps(result))
        self.assertEqual(result["selected"], 2, msg=json.dumps(result))
        self.assertEqual(result["selectedNodes"], 2, msg=json.dumps(result))
        self.assertEqual(result["cardBuckets"], ["Shared", "Shared"], msg=json.dumps(result))

    def test_canvas_notes_shift_click_multiselects_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_SHIFT_CLICK_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "A", "");
      var b = window.KyanbasuNotes.createNote(440, 240, "B", "");
      var aEl = document.querySelector('.tcNoteNode[data-note-id="'+a.id+'"]');
      var bEl = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
      aEl.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, button:0}));
      bEl.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, shiftKey:true}));
      bEl.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0, shiftKey:true}));
      bEl.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, button:0, shiftKey:true}));
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var out = {
          selected: window.KyanbasuNotes.selectedNotes().length,
          selectedNodes: document.querySelectorAll('.tcNoteNode.selected').length,
          selectedContents: window.KyanbasuNotes.selectedNotes().map(function(id){
            return window.KyanbasuNotes.notes().filter(function(n){ return n.id === id; })[0].content;
          }).sort(),
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["selected"], 2)
        self.assertEqual(result["selectedNodes"], 2)
        self.assertEqual(result["selectedContents"], ["A", "B"])
        self.assertEqual(result["console"], "")

    def test_canvas_notes_drag_lasso_multiselects_notes(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_LASSO_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      window.KyanbasuNotes.createNote(180, 240, "A", "");
      window.KyanbasuNotes.createNote(440, 240, "B", "");
      window.KyanbasuNotes.createNote(760, 240, "C", "");
      var stage = document.getElementById('builderStage');
      var r = stage.getBoundingClientRect();
      function evt(type, x, y){
        stage.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, button:0, clientX:r.left+x, clientY:r.top+y}));
      }
      evt('mousedown', 120, 190);
      evt('mousemove', 690, 390);
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0, clientX:r.left+690, clientY:r.top+390}));
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var out = {
          selected: window.KyanbasuNotes.selectedNotes().length,
          selectedNodes: document.querySelectorAll('.tcNoteNode.selected').length,
          selectedContents: window.KyanbasuNotes.selectedNotes().map(function(id){
            return window.KyanbasuNotes.notes().filter(function(n){ return n.id === id; })[0].content;
          }).sort(),
          marqueeLeftovers: document.querySelectorAll('.tcNoteMarquee').length,
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["selected"], 2)
        self.assertEqual(result["selectedNodes"], 2)
        self.assertEqual(result["selectedContents"], ["A", "B"])
        self.assertEqual(result["marqueeLeftovers"], 0)
        self.assertEqual(result["console"], "")

    def test_canvas_notes_drag_moves_selected_note_group(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_GROUP_DRAG_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var a = window.KyanbasuNotes.createNote(180, 240, "A", "");
      var b = window.KyanbasuNotes.createNote(440, 240, "B", "");
      var c = window.KyanbasuNotes.createNote(760, 240, "C", "");
      window.KyanbasuNotes.selectNote(a.id);
      window.KyanbasuNotes.selectNote(b.id, true);
      var bEl = document.querySelector('.tcNoteNode[data-note-id="'+b.id+'"]');
      var head = bEl.querySelector('.tcNoteHead');
      head.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, clientX:450, clientY:250}));
      document.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, cancelable:true, button:0, clientX:540, clientY:300}));
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0, clientX:540, clientY:300}));
      if (typeof updateConsole === 'function') updateConsole();
        setTimeout(function(){
        var by = {};
        window.KyanbasuNotes.notes().forEach(function(n){ by[n.content] = n; });
        var aRect = document.querySelector('.tcNoteNode[data-note-id="'+by.A.id+'"]').getBoundingClientRect();
        var bRect = document.querySelector('.tcNoteNode[data-note-id="'+by.B.id+'"]').getBoundingClientRect();
        var out = {
          selected: window.KyanbasuNotes.selectedNotes().length,
          aMoved: Math.abs(by.A.x - 270) <= 60 && Math.abs(by.A.y - 290) <= 60,
          bMoved: Math.abs(by.B.x - 530) <= 60 && Math.abs(by.B.y - 290) <= 60,
          notOverlap: !(aRect.right > bRect.left && aRect.left < bRect.right && aRect.bottom > bRect.top && aRect.top < bRect.bottom),
          cMovedSlightly: Math.abs(by.C.x - 760) <= 80 && Math.abs(by.C.y - 240) <= 80,
          paths: document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink').length,
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["selected"], 2)
        self.assertTrue(result["aMoved"])
        self.assertTrue(result["bMoved"])
        self.assertTrue(result["notOverlap"])
        self.assertTrue(result["cMovedSlightly"])
        self.assertEqual(result["paths"], 0)
        self.assertEqual(result["console"], "")

    def test_canvas_notes_collapse_hides_descendants_and_restores_them(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_CANVAS_NOTES_COLLAPSE_HARNESS">
window.addEventListener('load', function(){
  setTimeout(function(){
    try{
      var root = window.KyanbasuNotes.createNote(180, 240, "Root", "");
      var a = window.KyanbasuNotes.createChildNote(root.id, "A", "");
      var b = window.KyanbasuNotes.createChildNote(root.id, "B", "");
      var c = window.KyanbasuNotes.createChildNote(a.id, "C", "");
      window.KyanbasuNotes.toggleCollapse(root.id);
      var collapsedVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length;
      var collapsedPaths = document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink[data-type="child"]').length;
      window.KyanbasuNotes.toggleCollapse(root.id);
      var expandedVisible = Array.prototype.slice.call(document.querySelectorAll('.tcNoteNode')).filter(function(el){ return el.style.display !== 'none'; }).length;
      var expandedPaths = document.querySelectorAll('#tcNoteLinksLayer path.tcNoteLink[data-type="child"]').length;
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var out = {
          notes: window.KyanbasuNotes.notes().length,
          links: window.KyanbasuNotes.links().length,
          collapsedVisible: collapsedVisible,
          collapsedPaths: collapsedPaths,
          expandedVisible: expandedVisible,
          expandedPaths: expandedPaths,
          collapseButtons: document.querySelectorAll('.tcNoteNode [data-note-collapse]').length,
          console: (document.getElementById('consoleText') || {}).value || ""
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 120);
    }catch(e){
      var pre2 = document.createElement('pre');
      pre2.id = 'e2e-out';
      pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
      document.body.appendChild(pre2);
    }
  }, 700);
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["notes"], 4)
        self.assertEqual(result["links"], 3)
        self.assertEqual(result["collapsedVisible"], 1)
        self.assertEqual(result["collapsedPaths"], 0)
        self.assertEqual(result["expandedVisible"], 4)
        self.assertEqual(result["expandedPaths"], 3)
        self.assertEqual(result["collapseButtons"], 4)
        self.assertEqual(result["console"], "")

    def test_kyanbasu_commands_core_includes_dependency_commands(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_DEP_COMMAND_CORE_HARNESS">
window.addEventListener('load', function(){
  try{
    var res = window.KyanbasuCommands.build({
      raw: "task task-a modify +next",
      stagedAdd: [{from:"task-a", to:"task-b"}],
      depExtraCmds: ["task task-a modify depends:-task-c"],
      uuidForShort: function(short){ return ({ "task-a":"uuid-a", "task-b":"uuid-b", "task-c":"uuid-c" })[short] || short; }
    });
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = res.text;
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        text = self._run_html_harness(html)
        self.assertNotIn("ERR:", text)
        self.assertIn("task 'task-a' modify '+next' 'depends:-task-c'", text)
        self.assertIn("task 'uuid-a' modify 'depends:uuid-b'", text)

    def test_kyanbasu_commands_core_handles_new_task_fold_states(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_NEW_TASK_CORE_HARNESS">
window.addEventListener('load', function(){
  try{
    var tasks = [
      {uuid:"new-add", short:"new-add", desc:"Add me", project:"Work", tags:["base"], due:"20260101T000000Z"},
      {uuid:"new-done", short:"new-done", desc:"Done me", project:"Home", tags:[]},
      {uuid:"new-del", short:"new-del", desc:"Delete me", project:"Home", tags:[]},
      {uuid:"new-mod", short:"new-mod", desc:"Mod me", project:"Inbox", tags:["old"]}
    ];
    var fold = {
      "new-done": {done:true, tags:{}, extra:[]},
      "new-del": {deleted:true, tags:{}, extra:[]},
      "new-mod": {project:"Later", due:"tomorrow", tags:{fresh:true}, extra:["priority:H"]}
    };
    var res = window.KyanbasuCommands.build({
      raw: window.KyanbasuCommands.rawTaskLines({tasks:tasks, fold:fold}).join("\\n")
    });
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = res.text;
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        text = self._run_html_harness(html)
        self.assertNotIn("ERR:", text)
        self.assertIn("task add 'Add me' 'project:Work' '+base' 'due:20260101T000000Z'", text)
        self.assertIn("task log 'Done me' 'project:Home'", text)
        self.assertNotIn("Delete me", text)
        self.assertIn("task add 'Mod me' 'project:Later' '+old' '+fresh' 'due:tomorrow' 'priority:H'", text)

    def test_new_task_sync_reconciles_staged_new_task_modifiers_via_command_core(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_NEW_TASK_SYNC_HARNESS">
window.addEventListener('load', function(){
  try{
    window.TASKS.push({
      uuid:"new-sync",
      short:"new-sync",
      desc:"Sync me",
      project:"Inbox",
      tags:["old"],
      has_depends:false
    });
    window.STAGED_CMDS = [
      "task new-sync modify project:Work +fresh due:tomorrow",
      "task new-sync done"
    ];
    if (typeof updateConsole === 'function') updateConsole();
    var out = (document.getElementById('consoleText') || {}).value || "";
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = JSON.stringify({text:out, staged:window.STAGED_CMDS, fold:window.FOLD && window.FOLD["new-sync"]});
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["staged"], [])
        self.assertTrue(result["fold"]["done"])
        self.assertIn("task log 'Sync me' 'project:Work' '+old' '+fresh' 'due:tomorrow'", result["text"])

    def test_kyanbasu_commands_core_handles_existing_task_ops(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)

        harness = """
<script id="E2E_EXISTING_TASK_CORE_HARNESS">
window.addEventListener('load', function(){
  try{
    var tasks = [
      {uuid:"uuid-mod", short:"mod", desc:"Mod", project:"Later", tags:["next"]},
      {uuid:"uuid-done", short:"done", desc:"Done", project:"Work", tags:["old"]},
      {uuid:"uuid-del", short:"del", desc:"Delete", project:"Work", tags:["old"]}
    ];
    var res = window.KyanbasuCommands.build({
      raw: window.KyanbasuCommands.rawTaskLines({
        tasks: tasks,
        initMainTag: {mod:"old", done:"old", del:"old"},
        initProject: {mod:"Work", done:"Work", del:"Work"},
        existingOps: {
          "uuid-mod": {mods:["due:tomorrow", "+next", "priority:H"]},
          "uuid-done": {done:true, mods:["due:ignored"]},
          "uuid-del": {deleted:true, mods:["due:ignored"]}
        }
      }).join("\\n")
    });
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = res.text;
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        text = self._run_html_harness(html)
        self.assertNotIn("ERR:", text)
        self.assertIn("task 'uuid-mod' modify 'project:Later' '-old' '+next' 'due:tomorrow' 'priority:H'", text)
        self.assertIn("task 'uuid-done' done", text)
        self.assertIn("task 'uuid-del' delete", text)
        self.assertNotIn("due:ignored", text)

    def test_runtime_existing_ops_flow_uses_command_core(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                        "short": "cccccccc",
                        "desc": "Existing",
                        "project": "Work",
                        "tags": ["old"],
                        "has_depends": False,
                    }
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 1, lambda *_: None)

        harness = """
<script id="E2E_EXISTING_OPS_RUNTIME_HARNESS">
window.addEventListener('load', function(){
  try{
    window.__EXISTING_OPS__ = window.EX_OPS = {
      "cccccccc-cccc-cccc-cccc-cccccccccccc": {done:false, deleted:false, mods:["due:tomorrow", "+focus"]}
    };
    window.TASKS[0].project = "Later";
    window.TASKS[0].tags = ["next"];
    if (typeof updateConsole === 'function') updateConsole();
    var out = (document.getElementById('consoleText') || {}).value || "";
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = out;
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        text = self._run_html_harness(html)
        self.assertNotIn("ERR:", text)
        self.assertIn("task 'cccccccc-cccc-cccc-cccc-cccccccccccc' modify 'project:Later' '-old' '+next' 'due:tomorrow' '+focus'", text)

    def test_build_commands_includes_staged_dependencies_without_base_monkey_patch(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Parent",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Child",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 2, lambda *_: None)
        self.assertNotIn("buildCommands monkey patch to include staged depends", html)
        self.assertNotIn("__buildCommandsPatched", html)

        harness = """
<script id="E2E_STAGED_DEP_COMMAND_HARNESS">
window.addEventListener('load', function(){
  try{
    window.stagedAdd = [{from:"aaaaaaaa", to:"bbbbbbbb"}];
    var out = (typeof buildCommands==='function') ? String(buildCommands()||'') : '';
    var pre = document.createElement('pre');
    pre.id = 'e2e-out';
    pre.textContent = out;
    document.body.appendChild(pre);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        self.assertIn("task 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' modify 'depends:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'", raw)

    def test_dependency_overlay_matches_console_with_deduped_core_text(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Parent",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Child",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                        "short": "cccccccc",
                        "desc": "Old child",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 3, lambda *_: None)

        harness = """
<script id="E2E_DEP_OVERLAY_PARITY_HARNESS">
window.addEventListener('load', function(){
  try{
    window.stagedAdd = [
      {from:"aaaaaaaa", to:"bbbbbbbb"},
      {from:"aaaaaaaa", to:"bbbbbbbb"}
    ];
    window.__depExtraCmds = [
      "task aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa modify depends:-cccccccc-cccc-cccc-cccc-cccccccccccc"
    ];
    window.STAGED_CMDS = [
      "task aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa modify depends:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    ];
    if (typeof updateConsole === 'function') updateConsole();
    setTimeout(function(){
      var out = {
        console: (document.getElementById('consoleText') || {}).value || "",
        overlay: (document.getElementById('depCmdPre') || {}).textContent || ""
      };
      var pre = document.createElement('pre');
      pre.id = 'e2e-out';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }, 350);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["console"], result["overlay"])
        self.assertEqual(result["console"].count("depends:bbbbbbbb"), 1)
        self.assertIn("task 'aaaaaaaa' modify 'depends:bbbbbbbb' 'depends:-cccccccc'", result["console"])

    def test_dependency_interactions_runtime_renders_single_handle_and_staged_path(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Parent",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Child",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 2, lambda *_: None)
        self.assertIn('id="FEATURE_DEPENDENCY_INTERACTIONS_V1"', html)
        self.assertNotIn("Minimal dep handle", html)
        self.assertNotIn("Dependency system (v0.7.7 strict)", html)
        self.assertNotIn("dep-handle counts (Chrome-optimized)", html)

        harness = """
<script id="E2E_DEP_INTERACTIONS_HARNESS">
window.addEventListener('load', function(){
  try{
    setTimeout(function(){
      var stage = document.getElementById('builderStage');
      function makeNode(uuid, shortId, left, top){
        var node = document.createElement('div');
        node.className = 'node';
        node.setAttribute('data-uuid', uuid);
        node.setAttribute('data-short', shortId);
        node.style.position = 'absolute';
        node.style.left = left + 'px';
        node.style.top = top + 'px';
        node.style.width = '140px';
        node.style.height = '70px';
        node.textContent = shortId;
        stage.appendChild(node);
        if (typeof attachDepHandleToNode === 'function') attachDepHandleToNode(node);
      }
      makeNode("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "aaaaaaaa", 120, 120);
      makeNode("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "bbbbbbbb", 320, 240);
      window.stagedAdd = [{from:"aaaaaaaa", to:"bbbbbbbb"}];
      if (typeof drawLinks === 'function') drawLinks();
      if (typeof updateConsole === 'function') updateConsole();
      setTimeout(function(){
        var out = {
          handles: document.querySelectorAll('#builderStage [data-short] > .depHandle').length,
          wiredHandles: Array.prototype.filter.call(document.querySelectorAll('#builderStage [data-short] > .depHandle'), function(h){ return !!h.__depInteractionWired; }).length,
          parentHandles: document.querySelectorAll('#builderStage [data-short="aaaaaaaa"] > .depHandle').length,
          childHandles: document.querySelectorAll('#builderStage [data-short="bbbbbbbb"] > .depHandle').length,
          stagedPaths: document.querySelectorAll('#depStagedOverlay path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').length,
          stagedMarker: (document.querySelector('#depStagedOverlay path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]') || {}).getAttribute && document.querySelector('#depStagedOverlay path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').getAttribute('marker-end'),
          stagedDirectionFrom: (document.querySelector('#depStagedOverlay path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]') || {}).getAttribute && document.querySelector('#depStagedOverlay path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').getAttribute('data-direction-from'),
          stagedSources: document.querySelectorAll('#depStagedOverlay .depDirectionSource').length,
          stagedArrows: document.querySelectorAll('#depStagedOverlay .depDirectionArrow').length,
          stagedChevrons: document.querySelectorAll('#depStagedOverlay .depDirectionChevron').length,
          commandText: window.KyanbasuCommands.runtimeCommandText(window, {short:true})
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 350);
    }, 500);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["handles"], 2)
        self.assertEqual(result["wiredHandles"], 2)
        self.assertEqual(result["parentHandles"], 1)
        self.assertEqual(result["childHandles"], 1)
        self.assertEqual(result["stagedPaths"], 1)
        self.assertIsNone(result["stagedMarker"])
        self.assertEqual(result["stagedDirectionFrom"], "bbbbbbbb")
        self.assertEqual(result["stagedSources"], 1)
        self.assertEqual(result["stagedArrows"], 1)
        self.assertEqual(result["stagedChevrons"], 1)
        self.assertIn("task 'aaaaaaaa' modify 'depends:bbbbbbbb'", result["commandText"])

    def test_dependency_edges_runtime_renders_existing_edges_and_keeps_pulses_opt_in(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Parent",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Child",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                        "short": "cccccccc",
                        "desc": "Staged child",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                ],
                "graph": {
                    "edges": [{"from": "aaaaaaaa", "to": "bbbbbbbb"}],
                    "parent_current_deps": {},
                    "child_to_parents": {},
                },
            }
        )
        html = build_runtime_html(base_html, payload, 3, lambda *_: None)
        self.assertIn('id="FEATURE_DEPENDENCY_EDGES_V1"', html)
        self.assertNotIn("dep pulses: animate energy", html)
        self.assertNotIn("draw solid existing edges with robust anchors", html)

        harness = """
<script id="E2E_DEP_EDGES_HARNESS">
window.addEventListener('load', function(){
  try{
    setTimeout(function(){
      var stage = document.getElementById('builderStage');
      function makeNode(uuid, shortId, left, top){
        var node = document.createElement('div');
        node.className = 'node';
        node.setAttribute('data-uuid', uuid);
        node.setAttribute('data-short', shortId);
        node.style.position = 'absolute';
        node.style.left = left + 'px';
        node.style.top = top + 'px';
        node.style.width = '140px';
        node.style.height = '70px';
        node.textContent = shortId;
        stage.appendChild(node);
        if (typeof attachDepHandleToNode === 'function') attachDepHandleToNode(node);
      }
      makeNode("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "aaaaaaaa", 120, 120);
      makeNode("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "bbbbbbbb", 340, 230);
      makeNode("cccccccc-cccc-cccc-cccc-cccccccccccc", "cccccccc", 560, 330);
      if (typeof window.KyanbasuPerfReset === 'function') window.KyanbasuPerfReset();
      window.EXIST_EDGES = [{from:"aaaaaaaa", to:"bbbbbbbb"}];
      window.stagedAdd = [{from:"bbbbbbbb", to:"cccccccc"}];
      if (typeof drawLinks === 'function') drawLinks();
      if (typeof drawLinks === 'function') drawLinks();
      setTimeout(function(){
        var idlePulseGroups = document.querySelectorAll('#depPulseOverlay').length;
        var idlePulses = document.querySelectorAll('#depPulseOverlay .pulse-dot').length;
        var idlePerf = window.KyanbasuDiagnostics ? window.KyanbasuDiagnostics().perfSummary : null;
        document.dispatchEvent(new KeyboardEvent('keydown', {key:'p', bubbles:true}));
        setTimeout(function(){
        var out = {
          existingGroups: document.querySelectorAll('#depExistingEdges').length,
          existingPaths: document.querySelectorAll('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').length,
          existingMarker: (document.querySelector('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]') || {}).getAttribute && document.querySelector('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').getAttribute('marker-end'),
          existingDirectionFrom: (document.querySelector('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]') || {}).getAttribute && document.querySelector('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').getAttribute('data-direction-from'),
          existingSources: document.querySelectorAll('#depExistingEdges .depDirectionSource').length,
          existingArrows: document.querySelectorAll('#depExistingEdges .depDirectionArrow').length,
          existingChevrons: document.querySelectorAll('#depExistingEdges .depDirectionChevron').length,
          existingStroke: (document.querySelector('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]') || {}).style ? document.querySelector('#depExistingEdges path[data-from="aaaaaaaa"][data-to="bbbbbbbb"]').style.stroke : "",
          existingGradient: document.querySelectorAll('#builderLinks defs linearGradient[id^="depGradExisting"] stop').length,
          stagedGroups: document.querySelectorAll('#depStagedOverlay').length,
          stagedPaths: document.querySelectorAll('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]').length,
          stagedMarker: (document.querySelector('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]') || {}).getAttribute && document.querySelector('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]').getAttribute('marker-end'),
          stagedDirectionFrom: (document.querySelector('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]') || {}).getAttribute && document.querySelector('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]').getAttribute('data-direction-from'),
          stagedSources: document.querySelectorAll('#depStagedOverlay .depDirectionSource').length,
          stagedArrows: document.querySelectorAll('#depStagedOverlay .depDirectionArrow').length,
          stagedChevrons: document.querySelectorAll('#depStagedOverlay .depDirectionChevron').length,
          stagedStroke: (document.querySelector('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]') || {}).style ? document.querySelector('#depStagedOverlay path[data-from="bbbbbbbb"][data-to="cccccccc"]').style.stroke : "",
          stagedGradient: document.querySelectorAll('#builderLinks defs linearGradient[id^="depGradStaged"] stop').length,
          directionGroup: document.querySelectorAll('#depDirectionHints').length,
          arrowMarkerWidth: document.querySelector('#depArrow') ? document.querySelector('#depArrow').getAttribute('markerWidth') : null,
          arrowMarkerHeight: document.querySelector('#depArrow') ? document.querySelector('#depArrow').getAttribute('markerHeight') : null,
          directionHints: document.querySelectorAll('#depDirectionHints .depDirectionHint').length,
          textHints: document.querySelectorAll('#depDirectionHints .depDirectionText').length,
          textTrails: document.querySelectorAll('#depDirectionHints .depDirectionTrail').length,
          idlePulseGroups: idlePulseGroups,
          idlePulses: idlePulses,
          idleObserverCallbacks: idlePerf ? idlePerf.observers.callbacks : -1,
          idleObserverRecords: idlePerf ? idlePerf.observers.records : -1,
          idleRefreshCalls: idlePerf ? idlePerf.topFunctions.filter(function(x){ return x.name === 'refreshDepHandleLetters'; }).reduce(function(n, x){ return n + x.calls; }, 0) : -1,
          pulseGroups: document.querySelectorAll('#depPulseOverlay').length,
          pulses: document.querySelectorAll('#depPulseOverlay .pulse-dot').length,
          api: !!window.KyanbasuDependencyEdges
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
        }, 120);
      }, 450);
    }, 500);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertTrue(result["api"])
        self.assertEqual(result["existingGroups"], 1)
        self.assertEqual(result["existingPaths"], 1)
        self.assertIsNone(result["existingMarker"])
        self.assertEqual(result["existingDirectionFrom"], "bbbbbbbb")
        self.assertEqual(result["existingSources"], 1)
        self.assertEqual(result["existingArrows"], 1)
        self.assertEqual(result["existingChevrons"], 1)
        self.assertIn("depGradExisting", result["existingStroke"])
        self.assertGreaterEqual(result["existingGradient"], 3, msg=json.dumps(result))
        self.assertEqual(result["stagedGroups"], 1)
        self.assertEqual(result["stagedPaths"], 1)
        self.assertIsNone(result["stagedMarker"])
        self.assertEqual(result["stagedDirectionFrom"], "cccccccc")
        self.assertEqual(result["stagedSources"], 1)
        self.assertEqual(result["stagedArrows"], 1)
        self.assertEqual(result["stagedChevrons"], 1)
        self.assertIn("depGradStaged", result["stagedStroke"])
        self.assertGreaterEqual(result["stagedGradient"], 3, msg=json.dumps(result))
        self.assertEqual(result["directionGroup"], 0, msg=json.dumps(result))
        self.assertIsNone(result["arrowMarkerWidth"])
        self.assertIsNone(result["arrowMarkerHeight"])
        self.assertEqual(result["directionHints"], 0, msg=json.dumps(result))
        self.assertEqual(result["textHints"], 0, msg=json.dumps(result))
        self.assertEqual(result["textTrails"], 0, msg=json.dumps(result))
        self.assertEqual(result["idlePulseGroups"], 0)
        self.assertEqual(result["idlePulses"], 0)
        self.assertLess(result["idleObserverCallbacks"], 200, msg=json.dumps(result))
        self.assertLess(result["idleObserverRecords"], 2500, msg=json.dumps(result))
        self.assertLess(result["idleRefreshCalls"], 20, msg=json.dumps(result))
        self.assertEqual(result["pulseGroups"], 0)
        self.assertEqual(result["pulses"], 0)

    def test_project_picker_runtime_opens_and_lists_projects(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps(
            {
                "tasks": [
                    {
                        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "short": "aaaaaaaa",
                        "desc": "Alpha",
                        "project": "Work",
                        "tags": [],
                        "has_depends": False,
                    },
                    {
                        "uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "short": "bbbbbbbb",
                        "desc": "Beta",
                        "project": "Home",
                        "tags": [],
                        "has_depends": False,
                    },
                ],
                "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}},
            }
        )
        html = build_runtime_html(base_html, payload, 2, lambda *_: None)
        self.assertIn('id="PROJECT_PICKER_V2_CSS"', html)
        self.assertIn('id="PROJECT_PICKER_V2_JS"', html)
        self.assertNotIn("<!-- PROJECT_PICKER_V2_CSS -->", html)
        self.assertNotIn("<!-- PROJECT_PICKER_V2_JS -->", html)
        self.assertNotIn("<!-- PROJECT_PICKER_V2_BIND -->", html)

        harness = """
<script id="E2E_PROJECT_PICKER_HARNESS">
window.addEventListener('load', function(){
  try{
    setTimeout(function(){
      window.showProjectPickerV2();
      setTimeout(function(){
        var out = {
          overlay: document.querySelectorAll('.projPickOverlay').length,
          items: Array.prototype.map.call(document.querySelectorAll('.projPickItem .name'), function(el){ return el.textContent; }),
          selectedText: (document.querySelector('.projPickFooter') || {}).textContent || ''
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 100);
    }, 250);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["overlay"], 1)
        self.assertEqual(result["items"], ["Home", "Work"])
        self.assertIn("0 selected", result["selectedText"])

    def test_quickfix_add_render_runtime_exposes_parser_and_optimistic_add(self):
        base_html = Path("kyanbasu/templates/kyanbasu.base.html").read_text(encoding="utf-8")
        payload = json.dumps({"tasks": [], "graph": {"edges": [], "parent_current_deps": {}, "child_to_parents": {}}})
        html = build_runtime_html(base_html, payload, 0, lambda *_: None)
        self.assertIn('id="FEATURE_QUICKFIX_ADD_RENDER_V1"', html)
        self.assertNotIn('<script id="FEATURE_QUICKFIX_ADD_RENDER_V1">(function(){\n  if (window.__FEATURE_QUICKFIX_ADD_RENDER_V1__)', base_html)

        harness = """
<script id="E2E_QUICKFIX_ADD_HARNESS">
window.addEventListener('load', function(){
  try{
    setTimeout(function(){
      var parsed = window.KyanbasuQuickAdd.parseAdd("task add Review report project:Work +next due:tomorrow");
      var ok = window.KyanbasuQuickAdd.optimisticAdd("task add Review report project:Work +next due:tomorrow");
      setTimeout(function(){
        var node = document.querySelector('#builderStage .node[data-uuid^="new-"]');
        var out = {
          parsed: parsed,
          ok: ok,
          hasNode: !!node,
          nodeProject: node && node.getAttribute('data-proj'),
          nodeText: node ? node.textContent : ''
        };
        var pre = document.createElement('pre');
        pre.id = 'e2e-out';
        pre.textContent = JSON.stringify(out);
        document.body.appendChild(pre);
      }, 250);
    }, 350);
  }catch(e){
    var pre2 = document.createElement('pre');
    pre2.id = 'e2e-out';
    pre2.textContent = 'ERR:' + (e && e.message ? e.message : String(e));
    document.body.appendChild(pre2);
  }
});
</script>
"""
        html = html.replace("</body>", harness + "\n</body>")
        raw = self._run_html_harness(html)
        self.assertNotIn("ERR:", raw)
        result = json.loads(raw)
        self.assertEqual(result["parsed"]["desc"], "Review report")
        self.assertEqual(result["parsed"]["project"], "Work")
        self.assertEqual(result["parsed"]["tags"], ["next"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["hasNode"])
        self.assertIn("Review report", result["nodeText"])


if __name__ == "__main__":
    unittest.main()
