from __future__ import annotations
import argparse, hashlib, os, re, tempfile
from pathlib import Path
from wuxing.domain.enums import ResultStatus, WritePolicy
from wuxing.domain.models import ScrapeRequest
from wuxing.reporting.success import format_success_line
from wuxing.services.batch import BatchService
from wuxing.storage.file_lock import exclusive_file_lock
from .common import DEFAULT_SUCCESS_DIR, append_success_lines, build_runtime

MD = re.compile(r'^\s*失败\s+(?P<name>[^\[]+?)\s+\[(?P<url>https?://[^\]]+)\]\([^)]*\)\s+方向:\s*(?P<region>top|bottom)\s+期数:\s*0*(?P<period>\d+)\s*$')
PLAIN = re.compile(r'^\s*失败\s+(?P<name>.+?)\s+(?P<url>https?://\S+)\s+方向:\s*(?P<region>top|bottom)\s+期数:\s*0*(?P<period>\d+)\s*$')

def _parse(path):
    text = Path(path).read_text(encoding='utf-8-sig'); lines = text.splitlines(keepends=True)
    starts = [i for i, x in enumerate(lines) if x.lstrip().startswith('失败') and not x.lstrip().startswith('失败分类')]
    out=[]
    for n, start in enumerate(starts):
        m = MD.match(lines[start].rstrip('\r\n')) or PLAIN.match(lines[start].rstrip('\r\n'))
        if not m: raise ValueError(f'失败记录格式无法识别：第 {start+1} 行')
        d=m.groupdict(); out.append({'ordinal':n,'start':start,'end':starts[n+1] if n+1<len(starts) else len(lines),'name':d['name'].strip(),'url':d['url'],'region':d['region'],'period':int(d['period'])})
    if not out: raise ValueError(f'失败 TXT 没有可处理记录：{path}')
    periods={x['period'] for x in out}
    if len(periods)!=1: raise ValueError(f'失败 TXT 包含多个期数，拒绝混跑：{sorted(periods)}')
    return text, out

def load_failure_records(path): return tuple(_parse(Path(path))[1])

def resolve_sites(records, runtime):
    result=[]
    for r in records:
        found=[s for s in runtime.sites if s.name==r['name'] and s.url==r['url'] and s.region.value==r['region']]
        if len(found)!=1: raise ValueError(f"失败记录无法唯一匹配正式站点：{r['name']}")
        result.append((r,found[0]))
    return result

def _hash(p): return hashlib.sha256(p.read_bytes() if p.exists() else b'').hexdigest()

def _remove(path, identity, expected):
    with exclusive_file_lock(path):
        if _hash(path)!=expected: raise RuntimeError('失败 TXT 在处理期间发生变化，已停止写入')
        _, records=_parse(path); matches=[x for x in records if (x['name'],x['url'],x['region'],x['period'])==identity]
        if not matches: raise RuntimeError('失败记录已被外部修改，已停止写入')
        r=matches[0]
        lines=path.read_text(encoding='utf-8-sig').splitlines(keepends=True); payload=''.join(lines[:r['start']]+lines[r['end']:])
        temp=None
        try:
            with tempfile.NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=path.parent,delete=False) as f:
                f.write(payload); f.flush(); os.fsync(f.fileno()); temp=Path(f.name)
            os.replace(temp,path)
        finally:
            if temp: temp.unlink(missing_ok=True)
    return _hash(path)

def retry_failed(failure_path, output_dir=DEFAULT_SUCCESS_DIR, timeout_seconds=20, config_path=None, cache_path=None):
    path=Path(failure_path); _, records=_parse(path); expected=_hash(path); runtime=build_runtime(config_path,cache_path); selected=resolve_sites(records,runtime); period=records[0]['period']; service=BatchService(runtime.scrape_service); request=ScrapeRequest(periods=(period,),timeout_seconds=timeout_seconds,write_policy=WritePolicy.READ_ONLY); submit=ScrapeRequest(periods=(period,),timeout_seconds=timeout_seconds,write_policy=WritePolicy.UPDATE_CACHE); success=0; seen=set()
    for record,site in selected:
        identity=(record['name'],record['url'],record['region'],record['period'])
        if identity in seen: continue
        seen.add(identity)
        print(f"[验证] {site.name} | {period}期",flush=True)
        validation=service.run((site.site_id,),request,max_workers=1).results[0]
        if validation.status is not ResultStatus.SUCCESS: print(f'{site.name} 验证失败：{validation.reason}'); continue
        result=service.run((site.site_id,),request,max_workers=1).results[0]
        if result.status is not ResultStatus.SUCCESS: print(f'{site.name} 重抓失败：{result.reason}'); continue
        report=runtime.scrape_service.update_cache((result,),submit)
        if report.errors or getattr(report,'skipped_reason',None) or report.updated_sites!=1: print(f'{site.name} 缓存更新未完成：{report.errors or getattr(report,"skipped_reason",None)}'); continue
        append_success_lines(Path(output_dir)/f'{period}期-五行.txt',[format_success_line(result)])
        expected=_remove(path,identity,expected); success+=sum(1 for x in records if (x['name'],x['url'],x['region'],x['period'])==identity)
    remaining=len(records)-success; print(f'处理完成：成功 {success}，保留失败 {remaining}'); return 0 if not remaining else 1

def main(argv=None):
    p=argparse.ArgumentParser(description='只读取失败 TXT 并定向重抓失败站点'); p.add_argument('failure_txt'); p.add_argument('--output',default=str(DEFAULT_SUCCESS_DIR)); p.add_argument('--timeout',type=int,default=20); p.add_argument('--config'); p.add_argument('--cache'); a=p.parse_args(argv)
    try: return retry_failed(a.failure_txt,a.output,a.timeout,a.config,a.cache)
    except (OSError,ValueError,RuntimeError) as e: p.error(str(e))
if __name__=='__main__': raise SystemExit(main())
