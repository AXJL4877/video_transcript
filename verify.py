#!/usr/bin/env python3
"""模块接入自检（通用模板 · Python 版）

读取同目录 module.json 的 capabilities[]，对每条能力跑一次真实探测，
用来兜底「接入时漏接小功能」：忘接 = 自检变红。

用法：
  python verify.py                          # 直连本模块（ports.json / local.defaultPort）
  python verify.py --base http://127.0.0.1:8795
  python verify.py --base http://localhost:5173 --prefix /ai-in-api   # 走宿主代理，验证宿主接入

退出码：全部通过=0；有 auto 探测失败=1。manual 项只提示、不影响退出码。
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 避免 ✓/中文 编码崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_args(argv):
    out = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--base":
            i += 1
            out["base"] = argv[i]
        elif a == "--prefix":
            i += 1
            out["prefix"] = argv[i]
        elif a.startswith("--base="):
            out["base"] = a[len("--base="):]
        elif a.startswith("--prefix="):
            out["prefix"] = a[len("--prefix="):]
        i += 1
    return out


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_base_url(manifest, cli_base):
    if cli_base:
        return cli_base.rstrip("/")
    service_id = manifest.get("id")
    registry_file = os.environ.get("SCENE_STUDIO_PORTS_FILE") or str(
        Path.home() / ".scene-studio" / "ports.json"
    )
    if os.path.exists(registry_file):
        try:
            reg = read_json(registry_file)
            entry = reg.get(service_id) or {}
            if entry.get("baseUrl"):
                return str(entry["baseUrl"]).rstrip("/")
        except Exception:
            pass
    port = (manifest.get("local") or {}).get("defaultPort") or 8000
    return f"http://127.0.0.1:{port}"


def deep_has(obj, dotted_key):
    cur = obj
    for k in dotted_key.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    return True


def run_probe(base_url, prefix, verify):
    path = f"{prefix}{verify['path']}"
    url = f"{base_url}{path}"
    method = (verify.get("method") or "GET").upper()
    data = None
    headers = {}
    if "body" in verify:
        data = json.dumps(verify["body"]).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    expect = verify.get("expect") or {}
    status = None
    body_text = None
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.status
            body_text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        body_text = e.read().decode("utf-8", "replace")
    except Exception as e:
        return False, f"{method} {path} 请求失败: {e}"

    problems = []
    if expect.get("status") is not None and status != expect["status"]:
        problems.append(f"状态码 {status}，期望 {expect['status']}")
    parsed = None
    if expect.get("jsonHas") or expect.get("jsonEquals"):
        try:
            parsed = json.loads(body_text)
        except Exception:
            problems.append("响应不是合法 JSON")
    if expect.get("jsonHas") and parsed is not None and not deep_has(parsed, expect["jsonHas"]):
        problems.append(f"缺少字段 {expect['jsonHas']}")
    if expect.get("jsonEquals") and parsed is not None:
        for k, v in expect["jsonEquals"].items():
            if parsed.get(k) != v:
                problems.append(f"{k}={json.dumps(parsed.get(k), ensure_ascii=False)}，期望 {json.dumps(v, ensure_ascii=False)}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{method} {path} OK"


def main():
    args = parse_args(sys.argv[1:])
    prefix = (args.get("prefix") or "").rstrip("/")
    here = Path(__file__).resolve().parent
    manifest_path = here / "module.json"
    if not manifest_path.exists():
        print("找不到 module.json")
        return 2
    manifest = read_json(manifest_path)
    caps = manifest.get("capabilities")
    if not isinstance(caps, list) or not caps:
        print("module.json 未声明 capabilities[]，无法自检（见 MODULE_SPEC.md §10）")
        return 2
    base_url = resolve_base_url(manifest, args.get("base"))

    print(f"\n== 模块接入自检: {manifest.get('name')} ({manifest.get('id')}) ==")
    print(f"目标: {base_url}" + (f"  代理前缀: {prefix}" if prefix else "") + "\n")

    failed = 0
    manual = []
    for cap in caps:
        must = cap.get("must_keep")
        tag = "[必须]" if must else "[可选]"
        verify = cap.get("verify") or {}
        if verify.get("manual"):
            manual.append(cap)
            print(f"  ~ {tag} {cap.get('id')}: 需人工核对")
            continue
        if not verify.get("path"):
            print(f"  ? {tag} {cap.get('id')}: 无探测定义，跳过")
            continue
        ok, detail = run_probe(base_url, prefix, verify)
        mark = "\u2713" if ok else "\u2717"
        if not ok:
            failed += 1
        print(f"  {mark} {tag} {cap.get('id')}: {detail}")

    if manual:
        print("\n-- 人工核对项（自动探测无法覆盖，接入时逐条确认）--")
        for cap in manual:
            print(f"  [ ] {cap.get('id')}: {cap.get('desc')}")
            print(f"      验收: {cap['verify']['manual']}")

    print("")
    if failed > 0:
        print(f"自检未通过：{failed} 项能力探测失败。若刚接入，请确认服务已启动、宿主已代理对应路径。")
        return 1
    print("自检通过：所有自动探测项 OK。别忘了逐条确认上面的人工核对项。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
