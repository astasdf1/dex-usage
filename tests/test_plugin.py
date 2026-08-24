from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CLI=ROOT/"scripts/dex_usage.py"
class PluginSmokeTest(unittest.TestCase):
    def run_cli(self,home:Path,*args:str,env=None):
        return subprocess.run([sys.executable,str(CLI),"--home",str(home),*args],text=True,input="{}",capture_output=True,env=env,check=False)
    def test_manifest_hooks_and_skills(self):
        manifest=json.loads((ROOT/".claude-plugin/plugin.json").read_text());self.assertEqual(manifest["name"],"dex-usage")
        marketplace=json.loads((ROOT/".claude-plugin/marketplace.json").read_text());self.assertEqual(marketplace["name"],"dex-usage-marketplace");self.assertEqual(marketplace["plugins"][0]["name"],"dex-usage")
        hooks=json.loads((ROOT/"hooks/hooks.json").read_text())["hooks"]
        startup=hooks["SessionStart"][0]["hooks"][0]
        self.assertNotIn("async",startup);self.assertEqual(startup["timeout"],8);self.assertEqual(startup["args"][1],"hook-startup");self.assertIn("${CLAUDE_PLUGIN_ROOT}",startup["args"][0])
        prompt=hooks["UserPromptSubmit"][0]["hooks"][0]
        self.assertTrue(prompt["async"]);self.assertEqual(prompt["args"][1],"hook-warm");self.assertIn("${CLAUDE_PLUGIN_ROOT}",prompt["args"][0])
        self.assertEqual({p.parent.name for p in (ROOT/"skills").glob("*/SKILL.md")},{"usage-all","refresh","doctor","setup"})
    def test_fresh_home_no_node_flowdesk(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);env={"HOME":raw,"PATH":"/usr/bin:/bin","PYTHONPATH":"","DEX_USAGE_HTTP_TIMEOUT":"0.2"}
            result=self.run_cli(home,"refresh",env=env);self.assertEqual(result.returncode,0,result.stderr);data=json.loads(result.stdout)
            self.assertEqual([data[p]["alert_level"] for p in ("claude","openai","gemini")],["unknown"]*3)
            status=self.run_cli(home,"statusline",env=env);self.assertEqual(status.stdout.strip(),"usage C 5h:? 7d:? | O 5h:? 7d:? | G 5h:? 7d:?")
    def test_statusline_reads_cache_only(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);cache=home/".cache/dex-usage/usage.json";cache.parent.mkdir(parents=True);cache.write_text(json.dumps({"schema_version":"dex.provider_usage_cache.v1","captured_at":"2026-01-01T00:00:00Z","claude":{"remaining_percent":10},"openai":{"remaining_percent":20},"gemini":{"alert_level":"unknown"}}))
            env=os.environ|{"HOME":raw,"PATH":""};result=self.run_cli(home,"statusline",env=env);self.assertEqual(result.returncode,0);self.assertIn("C 5h:? 7d:? legacy:10%",result.stdout)
    def test_startup_refresh_is_unconditional_but_prompt_warm_honors_ttl(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);cache=home/".cache/dex-usage/usage.json";cache.parent.mkdir(parents=True);cache.write_text(json.dumps({"schema_version":"dex.provider_usage_cache.v2","captured_at":"2999-01-01T00:00:00Z","claude":{"remaining_percent":10},"openai":{"remaining_percent":20},"gemini":{"remaining_percent":30}}))
            env={"HOME":raw,"PATH":"/usr/bin:/bin","PYTHONPATH":"","DEX_USAGE_HTTP_TIMEOUT":"0.01"}
            before=cache.read_text();warm=self.run_cli(home,"hook-warm",env=env);self.assertEqual(warm.returncode,0,warm.stderr);self.assertEqual(cache.read_text(),before)
            startup=self.run_cli(home,"hook-startup",env=env);self.assertEqual(startup.returncode,0,startup.stderr);self.assertNotEqual(cache.read_text(),before)

    def test_refresh_keeps_last_known_provider_value_on_transient_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw); cache=home/".cache/dex-usage/usage.json"; cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({"schema_version":"dex.provider_usage_cache.v2","captured_at":"2026-01-01T00:00:00Z","claude":{"remaining_percent":37,"windows":{"five_hour":{"remaining_percent":37,"reset_time":"2999-01-01T00:00:00Z"},"one_week":{"remaining_percent":61}}},"openai":{"alert_level":"unknown"},"gemini":{"alert_level":"unknown"}}))
            env={"HOME":raw,"PATH":"/usr/bin:/bin","PYTHONPATH":"","DEX_USAGE_HTTP_TIMEOUT":"0.01"}
            result=self.run_cli(home,"refresh",env=env); self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(result.stdout)["claude"]; self.assertEqual(value["remaining_percent"],37); self.assertTrue(value["stale"])
    def test_setup_compose_and_conflict(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);settings=home/".claude/settings.json";settings.parent.mkdir();settings.write_text(json.dumps({"statusLine":{"type":"command","command":"printf old","padding":2}}))
            preview=self.run_cli(home,"setup","--dry-run");self.assertEqual(preview.returncode,0,preview.stderr);self.assertNotIn("DEX_USAGE_STATUSLINE_V1",settings.read_text());self.assertFalse((home/".cache").exists())
            result=self.run_cli(home,"setup");self.assertEqual(result.returncode,0,result.stderr);configured=json.loads(settings.read_text());command=configured["statusLine"]["command"];self.assertIn("DEX_USAGE_STATUSLINE_V1",command);self.assertIn(str(home/".claude/dex-usage/statusline.py"),command);self.assertNotIn(str(ROOT),command);self.assertEqual(configured["statusLine"]["padding"],2);self.assertTrue((home/".claude/dex-usage/statusline-config.json").is_file());self.assertEqual(len(list(settings.parent.glob("settings.json.dex-usage.*.bak"))),1)
            composed=subprocess.run(command.split(" # ")[0],shell=True,text=True,input="{}",capture_output=True,env=os.environ|{"HOME":raw});self.assertEqual(composed.stdout.strip(),"old | usage C 5h:? 7d:? | O 5h:? 7d:? | G 5h:? 7d:?")
            removed=self.run_cli(home,"uninstall");self.assertEqual(removed.returncode,0,removed.stderr);self.assertEqual(json.loads(settings.read_text())["statusLine"],{"type":"command","command":"printf old","padding":2});self.assertFalse((home/".claude/dex-usage").exists())
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);self.assertEqual(self.run_cli(home,"setup").returncode,0);settings=home/".claude/settings.json";value=json.loads(settings.read_text());value["statusLine"]={"type":"command","command":"printf user-changed"};settings.write_text(json.dumps(value));removed=self.run_cli(home,"uninstall");self.assertEqual(removed.returncode,2);self.assertEqual(json.loads(settings.read_text())["statusLine"]["command"],"printf user-changed")
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);settings=home/".claude/settings.json";settings.parent.mkdir();original={"statusLine":{"type":"http","url":"x"}};settings.write_text(json.dumps(original));result=self.run_cli(home,"setup");self.assertEqual(result.returncode,2);self.assertEqual(json.loads(settings.read_text()),original)
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw);real=home/"real.json";real.write_text("{}\n");settings=home/".claude/settings.json";settings.parent.mkdir();settings.symlink_to(real);result=self.run_cli(home,"setup");self.assertEqual(result.returncode,2);self.assertEqual(real.read_text(),"{}\n")
    def test_packaging_guards_and_folder_install(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw);target=base/"team plugin";result=subprocess.run([sys.executable,str(ROOT/"scripts/install-folder.py"),str(target)],text=True,capture_output=True,check=False);self.assertEqual(result.returncode,0,result.stderr);self.assertTrue((target/".claude-plugin/plugin.json").is_file())
            again=subprocess.run([sys.executable,str(ROOT/"scripts/install-folder.py"),str(target)],capture_output=True,check=False);self.assertEqual(again.returncode,2)
            archive=base/"dex-usage.tar.gz";packed=subprocess.run([sys.executable,str(ROOT/"scripts/package.py"),"--out",str(archive)],capture_output=True,check=False);self.assertEqual(packed.returncode,0,packed.stderr);self.assertTrue(archive.is_file())
            with tarfile.open(archive) as bundle:
                members=bundle.getmembers();names={m.name for m in members};self.assertTrue(all(m.isfile() and not m.issym() and not m.islnk() for m in members));self.assertNotIn("dex-usage/tests/test_plugin.py",names);self.assertNotIn("dex-usage/scripts/package.py",names);self.assertNotIn("dex-usage/scripts/install-folder.py",names);self.assertIn("dex-usage/scripts/statusline.py",names)
        inside=ROOT/"dist/unsafe.tar.gz";result=subprocess.run([sys.executable,str(ROOT/"scripts/package.py"),"--out",str(inside)],capture_output=True,check=False);self.assertNotEqual(result.returncode,0);self.assertFalse(inside.exists())
    def test_tar_gzip_is_byte_deterministic_across_times_and_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw);archives=[]
            for index in range(2):
                fixture=base/f"source-{index}";shutil.copytree(ROOT,fixture)
                timestamp=1_700_000_000+(index*10_000)
                for path in fixture.rglob("*"):
                    if path.is_file():os.utime(path,(timestamp,timestamp));path.chmod(0o600 if index == 0 else 0o777)
                archive=base/f"bundle-{index}.tar.gz"
                result=subprocess.run([sys.executable,str(fixture/"scripts/package.py"),"--out",str(archive)],text=True,capture_output=True,check=False);self.assertEqual(result.returncode,0,result.stderr)
                archives.append(archive)
                if index == 0:time.sleep(1.1)
            digests=[hashlib.sha256(path.read_bytes()).hexdigest() for path in archives];self.assertEqual(digests[0],digests[1])
            header=archives[0].read_bytes()[:10];self.assertEqual(header[:3],b"\x1f\x8b\x08");self.assertEqual(header[3]&0x08,0);self.assertEqual(header[4:8],b"\0\0\0\0")
            with tarfile.open(archives[0],"r:gz") as bundle:
                members=bundle.getmembers();expected={f"dex-usage/{path}" for path in (
                    ".claude-plugin/marketplace.json",".claude-plugin/plugin.json","NOTICE.md","README.md","bin/dex-usage","hooks/hooks.json",
                    "lib/dex_usage/__init__.py","lib/dex_usage/claude.py","lib/dex_usage/cli.py","lib/dex_usage/common.py","lib/dex_usage/gemini.py","lib/dex_usage/openai.py","lib/dex_usage/runtime.py",
                    "scripts/dex_usage.py","scripts/statusline.py","skills/doctor/SKILL.md","skills/refresh/SKILL.md","skills/setup/SKILL.md","skills/usage-all/SKILL.md")}
                self.assertEqual({member.name for member in members},expected);self.assertEqual(len(members),19)
                self.assertTrue(all(member.isfile() and not member.issym() and not member.islnk() for member in members))
                self.assertTrue(all((member.uid,member.gid,member.uname,member.gname,member.mtime)==(0,0,"","",0) for member in members))
                executable={"dex-usage/bin/dex-usage","dex-usage/scripts/dex_usage.py"}
                self.assertTrue(all(member.mode==(0o755 if member.name in executable else 0o644) for member in members))
    def test_hostile_source_nodes_fail_closed_and_artifacts_are_excluded(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw);fixture=base/"plugin";shutil.copytree(ROOT,fixture);outside=base/"secret";outside.write_text("DO NOT PACKAGE")
            (fixture/"leak").symlink_to(outside);(fixture/".env").write_text("SECRET=x");(fixture/".DS_Store").write_text("junk");(fixture/"edit.swp").write_text("junk")
            target=base/"installed";archive=base/"hostile.tar.gz"
            folder=subprocess.run([sys.executable,str(fixture/"scripts/install-folder.py"),str(target)],text=True,capture_output=True,check=False);packed=subprocess.run([sys.executable,str(fixture/"scripts/package.py"),"--out",str(archive)],text=True,capture_output=True,check=False)
            self.assertEqual(folder.returncode,2,folder.stderr);self.assertFalse(target.exists());self.assertNotEqual(packed.returncode,0,packed.stderr);self.assertFalse(archive.exists())
            (fixture/"leak").unlink()
            if hasattr(os,"mkfifo"):
                os.mkfifo(fixture/"hostile.fifo")
                for tool,args in (("scripts/install-folder.py",[str(target)]),("scripts/package.py",["--out",str(archive)])):
                    hostile=subprocess.run([sys.executable,str(fixture/tool),*args],text=True,capture_output=True,timeout=5,check=False);self.assertNotEqual(hostile.returncode,0,hostile.stderr)
                self.assertFalse(target.exists());self.assertFalse(archive.exists())
    def test_allowlisted_link_is_never_followed(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw);fixture=base/"plugin";shutil.copytree(ROOT,fixture);outside=base/"replacement.py";outside.write_text("print('leaked')\n")
            allowlisted=fixture/"scripts/statusline.py";allowlisted.unlink();allowlisted.symlink_to(outside)
            for tool,args,output in (("scripts/install-folder.py",[str(base/"installed")],base/"installed"),("scripts/package.py",["--out",str(base/"bundle.tar.gz")],base/"bundle.tar.gz")):
                result=subprocess.run([sys.executable,str(fixture/tool),*args],text=True,capture_output=True,timeout=5,check=False);self.assertNotEqual(result.returncode,0,result.stderr);self.assertFalse(output.exists())
    def test_setup_refuses_symlinked_bundled_runner(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw);fixture=base/"plugin";shutil.copytree(ROOT,fixture);runner=fixture/"scripts/statusline.py";runner.unlink();runner.symlink_to(base/"outside.py");(base/"outside.py").write_text("print('unsafe')\n")
            home=base/"home";result=subprocess.run([sys.executable,str(fixture/"scripts/dex_usage.py"),"--home",str(home),"setup"],text=True,capture_output=True,check=False)
            self.assertEqual(result.returncode,2,result.stderr);self.assertFalse((home/".claude/settings.json").exists())
    def test_marketplace_cache_removal_and_local_plugin_dir_survive(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw);home=base/"home";home.mkdir();cache_v1=base/".claude/plugins/cache/dex-usage-marketplace/dex-usage/1.0.0";cache_v1.parent.mkdir(parents=True);shutil.copytree(ROOT,cache_v1)
            env=os.environ|{"HOME":str(home)};cli=cache_v1/"scripts/dex_usage.py";setup=subprocess.run([sys.executable,str(cli),"--home",str(home),"setup"],text=True,capture_output=True,env=env,check=False);self.assertEqual(setup.returncode,0,setup.stderr)
            settings=json.loads((home/".claude/settings.json").read_text());command=settings["statusLine"]["command"];self.assertNotIn(str(cache_v1),command)
            cache=home/".cache/dex-usage/usage.json";cache.parent.mkdir(parents=True);cache.write_text(json.dumps({"schema_version":"dex.provider_usage_cache.v1","claude":{"remaining_percent":7},"openai":{},"gemini":{}}));shutil.rmtree(cache_v1)
            rendered=subprocess.run(command.split(" # ")[0],shell=True,text=True,input="{}",capture_output=True,env=env,check=False);self.assertEqual(rendered.stdout.strip(),"usage C 5h:? 7d:? legacy:7% | O 5h:? 7d:? | G 5h:? 7d:?")
            local=base/"local plugin";shutil.copytree(ROOT,local);updated=subprocess.run([sys.executable,str(local/"scripts/dex_usage.py"),"--home",str(home),"setup"],text=True,capture_output=True,env=env,check=False);self.assertEqual(updated.returncode,0,updated.stderr);shutil.rmtree(local);rendered=subprocess.run(command.split(" # ")[0],shell=True,text=True,input="{}",capture_output=True,env=env,check=False);self.assertEqual(rendered.stdout.strip(),"usage C 5h:? 7d:? legacy:7% | O 5h:? 7d:? | G 5h:? 7d:?")

    def test_v2_windows_and_reset_times_are_compact(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw); cache=home/".cache/dex-usage/usage.json"; cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({"schema_version":"dex.provider_usage_cache.v2","captured_at":"2026-01-01T00:00:00Z","claude":{"windows":{"five_hour":{"remaining_percent":37,"reset_time":"2999-01-01T02:00:00Z"},"one_week":{"remaining_percent":61,"reset_time":"2999-01-05T00:00:00Z"}}},"openai":{"windows":{"five_hour":{"remaining_percent":55},"one_week":{"remaining_percent":28}}},"gemini":{"windows":{"five_hour":{"status":"unsupported"},"one_week":{"status":"unsupported"}}}}))
            result=self.run_cli(home,"statusline"); self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn("C 5h:37%/",result.stdout); self.assertIn("7d:61%/",result.stdout)
            self.assertIn("O 5h:55%/? 7d:28%/?",result.stdout); self.assertIn("G 5h:unsupported 7d:unsupported",result.stdout)

    def test_startup_syncs_managed_runner_without_rewriting_settings(self):
        with tempfile.TemporaryDirectory() as raw:
            home=Path(raw); self.assertEqual(self.run_cli(home,"setup").returncode,0)
            settings=home/".claude/settings.json"; before=settings.read_bytes(); runner=home/".claude/dex-usage/statusline.py"; runner.write_text("old\n")
            env={"HOME":raw,"PATH":"/usr/bin:/bin","PYTHONPATH":"","DEX_USAGE_HTTP_TIMEOUT":"0.01"}
            result=self.run_cli(home,"hook-startup",env=env); self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(settings.read_bytes(),before); self.assertEqual(runner.read_bytes(),(ROOT/"scripts/statusline.py").read_bytes())
if __name__=="__main__":unittest.main()
