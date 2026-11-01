"""Я выполняю unit, настоящий CLI, пять учебных изменений и source ZIP."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from settlement.contracts import PAYMENT_FIELDS
from settlement.examples import data, write_csv
from package_release import package
import duckdb


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
    def cli(*args, success=True):
        completed = subprocess.run([sys.executable,'-m','settlement',*map(str,args)],cwd=ROOT,text=True,encoding='utf-8',capture_output=True)
        if (completed.returncode == 0) != success or completed.returncode not in (0,2):
            raise RuntimeError(completed.stderr)
        if success: return json.loads(completed.stdout)
        if completed.stdout: raise RuntimeError('Я получил stdout при отказе')
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp); inputs=base/'inputs'
        cli('prepare','--out',inputs)
        cli('prepare','--out',inputs,success=False)
        def execute(name,*,tol=0,day='2026-11-01',payments=None,success=True,fail=False):
            args=['run','--orders',inputs/'orders.csv','--payments',payments or inputs/'payments.csv','--out',base/name,'--as-of',day,'--tolerance-minor',tol]
            if fail:args.append('--fail-before-publish')
            return cli(*args,success=success)
        baseline=execute('report')
        if (baseline['rows'],baseline['issues'])!=(9,7):raise RuntimeError('Я не подтвердил demo')
        initial=cli('inspect','--out',base/'report')
        execute('replay')
        if initial!=cli('inspect','--out',base/'replay'):raise RuntimeError('Я получил другой replay')
        execute('report',success=False)
        execute('failure',success=False,fail=True)
        if (base/'failure').exists() or list(base.glob('.settlement-stage-*')):raise RuntimeError('Я опубликовал неполный результат')
        if execute('tolerance1',tol=1)['issues']!=6:raise RuntimeError('Я не подтвердил допуск')
        if execute('tomorrow',day='2026-11-02')['rows']!=10:raise RuntimeError('Я не подтвердил дату')
        _, payments=data()
        def changed(name,rows):
            path=base/name;write_csv(path,PAYMENT_FIELDS,rows);return path
        no_refund=[p for p in payments if p[0]!='P4']
        if execute('no-refund',payments=changed('no-refund.csv',no_refund))['issues']!=6:raise RuntimeError('Я не подтвердил возврат')
        corrected=[(*p[:2],'RUB',*p[3:]) if p[0]=='P7' else p for p in payments]
        fixed=execute('currency-fixed',payments=changed('currency-fixed.csv',corrected))
        if (fixed['rows'],fixed['issues'])!=(8,5):raise RuntimeError('Я не подтвердил исправление валюты')
        conflict=[*payments,('P2','O100','RUB',4001,'capture','2026-11-01')]
        execute('conflict',payments=changed('conflict.csv',conflict),success=False)
        if (base/'conflict').exists():raise RuntimeError('Я принял конфликт ID')
    archive=package()
    if package()!=archive:raise RuntimeError('Я получил разные байты ZIP')
    print(json.dumps({'python':sys.version.split()[0],'duckdb':duckdb.__version__,'tests':result.testsRun,'demo':{'rows':baseline['rows'],'issues':baseline['issues'],'statuses':baseline['statuses']},'exercises':5,'logical_replay':True,'no_partial_output':True,'archive':archive},ensure_ascii=False))


if __name__=='__main__':main()
